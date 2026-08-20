import { DemoAgentInputSchema, DemoAgentOutputSchema } from '@testgen/contracts';
import type { LLMAdapter } from './llm/adapter.js';
import { createNodeRunner, aggregateUsage, type NodeRunRecord } from './node-runner.js';

export type WorkflowExecutorOptions = {
  llm: LLMAdapter;
  maxAttempts?: number;
  onNodeRun?: (record: NodeRunRecord) => void;
};

export type WorkflowExecutionResult = {
  output: { summary: string; review: string; recommendations: string[] };
  nodeRuns: NodeRunRecord[];
  usage: ReturnType<typeof aggregateUsage>;
};

export async function executeWorkflow(input: unknown, options: WorkflowExecutorOptions): Promise<WorkflowExecutionResult> {
  const parsed = DemoAgentInputSchema.parse(input);
  const { llm, maxAttempts = 1, onNodeRun } = options;
  const nodeRuns: NodeRunRecord[] = [];
  const record = (item: NodeRunRecord) => { nodeRuns.push(item); onNodeRun?.(item); };

  const prepareInput = createNodeRunner({
    nodeName: 'prepare_input',
    maxAttempts,
    onNodeRun: record,
    handler: async () => ({ parsed, usage: { inputTokens: 0, outputTokens: 0 } }),
  });

  const analyzeContent = createNodeRunner({
    nodeName: 'analyze_content',
    maxAttempts,
    onNodeRun: record,
    handler: async () => {
      const completion = await llm.complete({ prompt: `分析需求「${parsed.title}」：${parsed.content}，生成测试要点。` });
      return { summary: completion.text, usage: completion.usage };
    },
  });

  const reviewAnalysis = createNodeRunner({
    nodeName: 'review_analysis',
    maxAttempts,
    onNodeRun: record,
    handler: async () => {
      const completion = await llm.complete({ prompt: '评审分析结果，输出评审结论。' });
      return { review: completion.text, usage: completion.usage };
    },
  });

  const buildResult = createNodeRunner({
    nodeName: 'build_result',
    maxAttempts,
    onNodeRun: record,
    handler: async () => {
      const summary = await llm.complete({ prompt: '生成结果摘要。' });
      const review = await llm.complete({ prompt: '生成评审摘要。' });
      return { summary: summary.text, review: review.text, recommendations: ['补充边界场景', '确认验收标准'], usage: { inputTokens: 0, outputTokens: 0 } };
    },
  });

  const prepared = await prepareInput({} as never);
  const analyzed = await analyzeContent(prepared.parsed as never);
  const reviewed = await reviewAnalysis({ summary: analyzed.summary } as never);
  const output = await buildResult({ summary: reviewed.review } as never);

  const demoOutput = DemoAgentOutputSchema.parse({ summary: output.summary, review: output.review, recommendations: output.recommendations });
  const usage = aggregateUsage(nodeRuns);
  return { output: demoOutput, nodeRuns, usage };
}