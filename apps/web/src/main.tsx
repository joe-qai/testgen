import { createContext, useContext, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { StrictMode } from 'react';
import { BrowserRouter, Link, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import './styles.css';

type Run = { id: string; status: string; progress: number; workflowCode: string; createdAt: string };
type WorkflowEvent = { id: string; runId: string; sequence: number; eventType: string; nodeName: string | null; payload: Record<string, unknown>; createdAt: string };

const queryClient = new QueryClient();
const TOKEN_KEY = 'testgen.accessToken';
const api = async (path: string, options?: RequestInit) => (await fetch(path, options)).json();

function getToken() { return localStorage.getItem(TOKEN_KEY); }
function setToken(token: string) { localStorage.setItem(TOKEN_KEY, token); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }

const AuthContext = createContext<{ token: string | null; login: (email: string, password: string) => Promise<boolean>; logout: () => void }>({ token: null, login: async () => false, logout: () => {} });

function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => getToken());
  const login = async (email: string, password: string) => {
    const result = await api('/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) });
    if (result?.data?.accessToken) { setToken(result.data.accessToken); setTokenState(result.data.accessToken); return true; }
    return false;
  };
  const logout = () => { clearToken(); setTokenState(null); };
  return <AuthContext.Provider value={{ token, login, logout }}>{children}</AuthContext.Provider>;
}
function useAuth() { return useContext(AuthContext); }

function LoginPage() {
  const { token, login } = useAuth();
  const [email, setEmail] = useState('admin@example.com');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  if (token) return <Navigate to="/dashboard" replace />;
  const submit = async () => { setSubmitting(true); setError(null); const ok = await login(email, password); if (!ok) setError('邮箱或密码错误'); setSubmitting(false); };
  return <div className="login-wrap"><form className="login-card" onSubmit={(event) => { event.preventDefault(); submit(); }}>
    <h1>TestGen Agent</h1><p className="muted">登录后进入平台工作台</p>
    <label>邮箱<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
    <label>密码<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
    {error && <p className="error">{error}</p>}
    <button type="submit" disabled={submitting}>{submitting ? '登录中...' : '登录'}</button>
  </form></div>;
}

function Layout({ children }: { children: React.ReactNode }) { const { token, logout } = useAuth(); if (!token) return <Navigate to="/login" replace />; return <div className="app-shell"><aside><strong>TestGen Agent</strong><nav><Link to="/dashboard">工作台</Link><Link to="/projects">项目管理</Link><Link to="/workflow-runs">Agent 任务</Link><Link className="disabled" to="/requirements">需求管理（建设中）</Link><Link className="disabled" to="/cases">用例管理（建设中）</Link><Link className="disabled" to="/knowledge">RAG 知识库（建设中）</Link></nav></aside><main><header><span>当前组织：默认组织</span><span className="logout" onClick={logout}>退出登录　⌄</span></header>{children}</main></div>; }

function Dashboard() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [creating, setCreating] = useState(false);
  const createRun = async () => { setCreating(true); const result = await api('/api/v1/workflow-runs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ organizationId: 'demo-org', projectId: 'demo-project', idempotencyKey: `demo-${Date.now()}`, input: { title: '演示任务', content: '验证 Agent 工作流链路' } }) }); if (result.data) setRuns((items) => [result.data, ...items]); setCreating(false); };
  return <section><p className="eyebrow">AGENT PLATFORM</p><h1>工作台</h1><p className="muted">React + NestJS + LangGraph.js Agent 平台。</p><div className="toolbar"><button onClick={createRun} disabled={creating}>{creating ? '创建中...' : '创建演示 Agent 任务'}</button><Link className="button-link" to="/workflow-runs">查看全部任务</Link></div><div className="cards"><article><b>项目</b><strong>0</strong><span>当前组织项目</span></article><article><b>最近运行</b><strong>{runs.length}</strong><span>Workflow Run</span></article><article><b>系统状态</b><strong className="ok">正常</strong><span>API / Worker</span></article></div></section>;
}

function Projects() { return <section><p className="eyebrow">PROJECTS</p><h1>项目管理</h1><div className="panel"><p className="muted">项目 API 已提供基础列表、详情和创建接口。</p><button>创建项目</button></div></section>; }

function WorkflowRuns() {
  const [runs, setRuns] = useState<Run[]>([]);
  useEffect(() => { const load = async () => { const result = await api('/api/v1/workflow-runs'); setRuns(result.data ?? []); }; load(); const timer = setInterval(load, 5000); return () => clearInterval(timer); }, []);
  return <section><p className="eyebrow">WORKFLOW RUNS</p><h1>Agent 任务</h1><div className="panel">{runs.length === 0 ? <p className="muted">暂无运行记录，可从工作台创建演示任务。</p> : runs.map((run) => <Link className="run" to={`/workflow-runs/${run.id}`} key={run.id}><span>{run.workflowCode}</span><b>{run.status}</b><small>{run.id}</small></Link>)}</div></section>;
}

function RunDetail() {
  const { id } = useParams();
  const [run, setRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  useEffect(() => {
    if (!id) return;
    const load = async () => { const result = await api(`/api/v1/workflow-runs/${id}`); if (result.data) setRun(result.data); };
    load();
    const es = new EventSource(`/api/v1/workflow-runs/${id}/stream`);
    const onEvent = (raw: Event) => { try { const parsed: WorkflowEvent = JSON.parse((raw as MessageEvent).data); setEvents((prev) => [...prev, parsed]); } catch { /* ignore */ } };
    es.addEventListener('message', onEvent);
    es.addEventListener('RUN_STARTED', onEvent);
    es.addEventListener('NODE_STARTED', onEvent);
    es.addEventListener('NODE_PROGRESS', onEvent);
    es.addEventListener('RUN_COMPLETED', onEvent);
    es.addEventListener('RUN_FAILED', onEvent);
    return () => es.close();
  }, [id]);
  return <section><p className="eyebrow">RUN DETAIL</p><h1>运行详情</h1><div className="panel">{run ? <>
    <div className="run"><span>{run.workflowCode}</span><b>{run.status}</b><small>{run.id}</small></div>
    <p className="muted">进度：{run.progress}%</p>
    <h2>实时事件</h2>
    <ul className="events">{events.length === 0 ? <li className="muted">等待事件...</li> : events.map((item) => <li key={item.sequence}><b>{item.eventType}</b> <span>seq {item.sequence}</span></li>)}</ul>
  </> : <p className="muted">加载中...</p>}</div></section>;
}

function App() { return <AuthProvider><BrowserRouter><Routes><Route path="/login" element={<LoginPage />} /><Route path="/" element={<Layout><Dashboard /></Layout>} /><Route path="/dashboard" element={<Layout><Dashboard /></Layout>} /><Route path="/projects" element={<Layout><Projects /></Layout>} /><Route path="/workflow-runs" element={<Layout><WorkflowRuns /></Layout>} /><Route path="/workflow-runs/:id" element={<Layout><RunDetail /></Layout>} /><Route path="*" element={<Navigate to="/dashboard" replace />} /></Routes></BrowserRouter></AuthProvider>; }

createRoot(document.getElementById('root')!).render(<StrictMode><QueryClientProvider client={queryClient}><App /></QueryClientProvider></StrictMode>);