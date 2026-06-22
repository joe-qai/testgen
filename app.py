#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TestGen - AI测试用例生成平台 (重构版)
基于PRD需求规格说明书实现
"""

import os
import sys
import io
import logging
import uuid
import time
import threading
import json

from sqlalchemy import text

# 修复 Windows 控制台编码问题
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ==================== 使用统一日志工具 ====================
from src.utils import init_global_logging

init_global_logging()

from flask import Flask, send_from_directory, make_response, g, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit

from src.monitoring.error_response import ErrorResponse
from src.monitoring.metrics_collector import MetricsCollector

metrics_collector = MetricsCollector()

# 导入新模块
from src.database.models import init_database, get_session, init_scoped_session
from src.llm.adapter import LLMManager
from src.vectorstore.chroma_store import ChromaVectorStore
from src.services.generation_service import GenerationService
from src.api.routes import api_bp, init_services


def create_app():
    """应用工厂函数"""
    app = Flask(__name__)
    CORS(app)

    # 配置
    app.config["UPLOAD_FOLDER"] = "data/uploads"
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB
    app.config["UI_FOLDER"] = "src/ui"

    # 确保目录存在
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # ==================== 初始化数据库 ====================
    logging.info("正在初始化数据库...")
    engine = init_database("data/testgen.db")
    db_session = get_session(engine)
    init_scoped_session(engine)  # 初始化线程安全session

    # ==================== 初始化FTS5增量更新监听器 ====================
    logging.info("正在设置FTS5增量更新监听器...")
    try:
        from src.database.fts5_listeners import setup_fts5_listeners

        setup_fts5_listeners(engine)
        logging.info("FTS5监听器已设置")
    except Exception as e:
        logging.info(f"FTS5监听器设置失败: {e}")

    # ==================== 初始化LLM管理器 ====================
    logging.info("正在初始化LLM管理器...")
    llm_manager = LLMManager()

    # 从数据库加载LLM配置
    try:
        from src.database.models import LLMConfig

        configs = db_session.query(LLMConfig).filter(LLMConfig.is_active == 1).all()

        # 先加载所有配置
        for config in configs:
            llm_manager.add_config(
                name=config.name,
                provider=config.provider,
                base_url=config.base_url,
                api_key=config.api_key,
                model_id=config.model_id,
                timeout=config.timeout,
                is_default=bool(config.is_default),
            )
            logging.info(
                f"加载配置: {config.name} ({config.provider}) - {'[默认]' if config.is_default else ''}"
            )

        # 输出当前默认配置
        default_info = llm_manager.get_config_info()
        logging.info(
            f"已加载 {len(configs)} 个LLM配置，当前默认: {default_info.get('name', '无')}"
        )
    except Exception as e:
        logging.info(f"加载LLM配置失败: {e}")

    # 数据库列迁移：确保 prompt_templates 表有 version 和 change_log 字段
    try:
        from sqlalchemy import inspect, text

        inspector = inspect(engine)
        columns = [col["name"] for col in inspector.get_columns("prompt_templates")]
        if "version" not in columns:
            logging.info("正在添加 version 列到 prompt_templates 表...")
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE prompt_templates ADD COLUMN version INTEGER DEFAULT 1"
                    )
                )
                conn.commit()
            logging.info("  version 列添加完成")
        if "change_log" not in columns:
            logging.info("正在添加 change_log 列到 prompt_templates 表...")
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE prompt_templates ADD COLUMN change_log TEXT DEFAULT ''"
                    )
                )
                conn.commit()
            logging.info("  change_log 列添加完成")
        if "updated_at" not in columns:
            logging.info("正在添加 updated_at 列到 prompt_templates 表...")
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE prompt_templates ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"
                    )
                )
                conn.commit()
            logging.info("  updated_at 列添加完成")
    except Exception as e:
        logging.info(f"数据库列迁移失败: {e}")

    # 旧类型迁移：analyze -> requirement_analysis, review -> test_plan
    try:
        from src.database.models import PromptTemplate
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "UPDATE prompt_templates SET template_type = 'requirement_analysis' WHERE template_type = 'analyze'"
                )
            )
            if result.rowcount > 0:
                logging.info(
                    f"  迁移 {result.rowcount} 个 analyze 模板到 requirement_analysis"
                )
            result = conn.execute(
                text(
                    "UPDATE prompt_templates SET template_type = 'test_plan' WHERE template_type = 'review'"
                )
            )
            if result.rowcount > 0:
                logging.info(f"  迁移 {result.rowcount} 个 review 模板到 test_plan")
            conn.commit()
    except Exception as e:
        logging.info(f"旧类型迁移失败: {e}")

    # 初始化默认Prompt模板（使用新的 PromptTemplateService）
    try:
        from src.services.prompt_template_service import PromptTemplateService

        prompt_service = PromptTemplateService(db_session)
        initialized_count = prompt_service.initialize_default_prompts()
        if initialized_count > 0:
            logging.info(f"已初始化 {initialized_count} 个默认Prompt模板")
        else:
            logging.info("默认Prompt模板已存在，跳过初始化")
    except Exception as e:
        logging.info(f"初始化Prompt模板失败: {e}")

    # ==================== 初始化向量库 ====================
    logging.info("正在初始化向量库...")
    try:
        vector_store = ChromaVectorStore("data/chroma_db")
        logging.info("向量库初始化成功")
    except Exception as e:
        logging.info(f"向量库初始化失败: {e}")
        vector_store = None

    # ==================== 初始化生成服务 ====================
    logging.info("正在初始化生成服务...")
    generation_service = GenerationService(
        db_session=db_session, llm_manager=llm_manager, vector_store=vector_store
    )

    # ==================== 初始化SocketIO ====================
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

    # 存储SocketIO实例
    app.socketio = socketio

    # ==================== 注册API蓝图 ====================
    init_services(db_session, llm_manager, vector_store, generation_service, socketio)
    app.register_blueprint(api_bp)

    # ==================== WebSocket事件处理 ====================
    @socketio.on("connect", namespace="/progress")
    def handle_connect():
        emit("connected", {"status": "OK"})

    @socketio.on("subscribe", namespace="/progress")
    def handle_subscribe(data):
        task_id = data.get("task_id")
        if task_id:
            emit("subscribed", {"task_id": task_id, "status": "subscribed"})

    # ==================== 前端路由 ====================
    @app.route("/")
    def index():
        return send_from_directory(app.config["UI_FOLDER"], "testgen-app.html")

    @app.route("/chat")
    def chat_page():
        response = make_response(
            send_from_directory(app.config["UI_FOLDER"], "chat.html")
        )
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.route("/requirements")
    def requirements_page():
        return send_from_directory(app.config["UI_FOLDER"], "requirements.html")

    @app.route("/cases")
    def cases_page():
        return send_from_directory(app.config["UI_FOLDER"], "cases.html")

    @app.route("/rag")
    def rag_page():
        return send_from_directory(app.config["UI_FOLDER"], "rag.html")

    @app.route("/prompts")
    def prompts_page():
        return send_from_directory(app.config["UI_FOLDER"], "prompts.html")

    @app.route("/config")
    def config_page():
        return send_from_directory(app.config["UI_FOLDER"], "config.html")

    @app.route("/defects")
    def defects_page():
        return send_from_directory(app.config["UI_FOLDER"], "defects.html")

    @app.route("/autogen")
    def autogen_page():
        return send_from_directory(app.config["UI_FOLDER"], "testgen-app.html")

    @app.route("/langgraph")
    def langgraph_page():
        return send_from_directory(app.config["UI_FOLDER"], "testgen-app.html")

    @app.route("/<path:path>")
    def static_files(path):
        return send_from_directory(app.config["UI_FOLDER"], path)

    @app.route("/health/live")
    def health_live():
        return jsonify({"status": "alive"}), 200

    @app.route("/health/ready")
    def health_ready():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return jsonify({"status": "ready", "database": "connected"}), 200
        except Exception:
            return jsonify({"status": "not_ready", "database": "disconnected"}), 503

    @app.route("/metrics")
    def metrics():
        return jsonify(metrics_collector.get_metrics()), 200

    @app.before_request
    def assign_request_id():
        if 'X-Request-ID' in request.headers:
            g.request_id = request.headers['X-Request-ID']
        else:
            g.request_id = str(uuid.uuid4())
        g.start_time = time.time()

    @app.errorhandler(Exception)
    def handle_unhandled_exception(e):
        request_id = getattr(g, 'request_id', str(uuid.uuid4()))
        logging.error(f"Unhandled exception: {str(e)}", exc_info=True)

        if db_session:
            db_session.rollback()

        error_response = ErrorResponse.create(
            message="服务器内部错误",
            code="INTERNAL_ERROR",
            request_id=request_id
        )
        return jsonify(error_response), 500

    @app.after_request
    def normalize_error_response(response):
        if not request.path.startswith('/api'):
            return response

        if response.status_code < 400:
            if hasattr(g, 'start_time'):
                latency_ms = (time.time() - g.start_time) * 1000
                metrics_collector.record_request(response.status_code, latency_ms)
            return response

        try:
            data = response.get_json()
            if not data:
                if hasattr(g, 'start_time'):
                    latency_ms = (time.time() - g.start_time) * 1000
                    metrics_collector.record_request(response.status_code, latency_ms)
                return response

            request_id = getattr(g, 'request_id', str(uuid.uuid4()))

            if 'request_id' not in data:
                data['request_id'] = request_id

            if response.status_code >= 500 and 'error' in data:
                data['error'] = "服务器内部错误"

            if 'code' not in data:
                data['code'] = f"HTTP_{response.status_code}"

            response.data = json.dumps(data)
            response.content_type = 'application/json'
        except Exception:
            pass

        if hasattr(g, 'start_time'):
            latency_ms = (time.time() - g.start_time) * 1000
            metrics_collector.record_request(response.status_code, latency_ms)

        return response

    # 存储全局服务实例（用于测试和调试）
    app.db_session = db_session
    app.llm_manager = llm_manager
    app.vector_store = vector_store
    app.generation_service = generation_service

    logging.info("应用初始化完成！")
    return app, socketio


# 创建应用实例
app, socketio = create_app()

if __name__ == "__main__":
    import logging

    logging.info("=" * 60)
    logging.info("TestGen - AI测试用例生成平台")
    logging.info("基于PRD需求规格说明书 v0.1")
    logging.info("=" * 60)
    # 禁用 reloader 避免日志重复输出
    socketio.run(app, debug=True, host="0.0.0.0", port=5000, use_reloader=False, allow_unsafe_werkzeug=True)
