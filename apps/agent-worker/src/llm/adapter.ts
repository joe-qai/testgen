export type LLMUsage = { inputTokens?: number; outputTokens?: number };

export type LLMCompletionRequest = {
  prompt: string;
  maxTokens?: number;
  temperature?: number;
};

export type LLMCompletionResult = {
  text: string;
  usage?: LLMUsage;
};

export interface LLMAdapter {
  complete(request: LLMCompletionRequest): Promise<LLMCompletionResult>;
}

export class MockLLMAdapter implements LLMAdapter {
  constructor(private readonly responder: (prompt: string) => string = (prompt) => `Mock 生成结果（${prompt.slice(0, 40)}...）`) {}

  async complete(request: LLMCompletionRequest): Promise<LLMCompletionResult> {
    return { text: this.responder(request.prompt), usage: { inputTokens: Math.ceil(request.prompt.length / 4), outputTokens: 32 } };
  }
}

export function createMockLLMAdapter(): LLMAdapter {
  return new MockLLMAdapter();
}