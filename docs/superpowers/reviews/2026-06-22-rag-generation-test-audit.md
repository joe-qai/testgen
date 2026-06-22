# RAG 生成失败测试逻辑审查

| 测试 | 规格依据 | 结论 | 处置 |
|---|---|---|---|
| test_query_construction_with_points | 两层 RAG / ITEM 含测试点 | 实现缺陷 | 保留 |
| test_query_construction_without_points | 两层 RAG / ITEM 无测试点 | 实现缺陷 | 保留 |
| test_no_hybrid_retriever_returns_empty | 稳定降级 / 检索器不可用 | 实现缺陷 | 补充稳定结构断言 |
| test_query_optimizer_fallback | 稳定降级 / 优化器异常 | 实现缺陷 | 保留 |
| test_no_rag_results_placeholder | 稳定降级 / 无结果 | 测试陈旧 | evaluator 必须返回 no_results 后再断言占位文本 |
| test_citation_instruction_in_context | 引用提示 | 实现缺陷 | 保留 |
| test_defect_not_duplicated | 全局缺陷不重复 | 实现缺陷 | 保留 |
| test_low_similarity_triggers_expanded_retrieval | 低相似度单次扩检 | 测试错误 | mock 从三次返回改为两次并断言 top_k=[5, 10] |
| test_no_results_sets_degraded | 稳定降级 / 无结果 | 实现缺陷 | 保留 |
