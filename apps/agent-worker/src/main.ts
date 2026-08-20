import { Annotation, END, START, StateGraph } from '@langchain/langgraph';
import { DemoAgentInputSchema, DemoAgentOutputSchema } from '@testgen/contracts';

const State = Annotation.Root({
  input: Annotation<ReturnType<typeof DemoAgentInputSchema.parse>>(),
  summary: Annotation<string>({ reducer: (_, next) => next, default: () => '' }),
  review: Annotation<string>({ reducer: (_, next) => next, default: () => '' }),
  recommendations: Annotation<string[]>({ reducer: (_, next) => next, default: () => [] }),
});

type DemoState = typeof State.State;

const prepareInput = async (state: DemoState) => ({ input: DemoAgentInputSchema.parse(state.input) });
const analyzeContent = async (state: DemoState) => ({ summary: `已分析：${state.input.title}`, recommendations: ['补充边界场景', '确认验收标准'] });
const reviewAnalysis = async (state: DemoState) => ({ review: `评审完成：摘要长度 ${state.summary.length}` });
const buildResult = async (state: DemoState) => { DemoAgentOutputSchema.parse({ summary: state.summary, review: state.review, recommendations: state.recommendations }); return {}; };

export function buildDemoAgentWorkflow() {
  return new StateGraph(State).addNode('prepare_input', prepareInput).addNode('analyze_content', analyzeContent).addNode('review_analysis', reviewAnalysis).addNode('build_result', buildResult).addEdge(START, 'prepare_input').addEdge('prepare_input', 'analyze_content').addEdge('analyze_content', 'review_analysis').addEdge('review_analysis', 'build_result').addEdge('build_result', END).compile();
}

export async function runDemoAgent(input: unknown) {
  const parsed = DemoAgentInputSchema.parse(input);
  const result = await buildDemoAgentWorkflow().invoke({ input: parsed });
  return DemoAgentOutputSchema.parse({ summary: result.summary, review: result.review, recommendations: result.recommendations });
}

if (process.env.NODE_ENV !== 'test') console.log('Agent Worker ready: LangGraph.js demo workflow');
