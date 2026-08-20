import type { LLMAdapter, LLMCompletionRequest, LLMCompletionResult, LLMUsage } from './adapter.js';

export type OpenAILLMAdapterOptions = {
  apiKey: string;
  baseUrl?: string;
  model?: string;
  fetch?: typeof fetch;
};

export class OpenAILLMAdapter implements LLMAdapter {
  private readonly baseUrl: string;
  private readonly model: string;
  private readonly fetchImpl: typeof fetch;
  private readonly apiKey: string;

  constructor(options: OpenAILLMAdapterOptions) {
    this.baseUrl = (options.baseUrl ?? 'https://api.openai.com/v1').replace(/\/$/, '');
    this.model = options.model ?? 'gpt-4o-mini';
    this.fetchImpl = options.fetch ?? globalThis.fetch;
    this.apiKey = options.apiKey;
  }

  async complete(request: LLMCompletionRequest): Promise<LLMCompletionResult> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}/chat/completions`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${this.apiKey}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: this.model,
          messages: [{ role: 'user', content: request.prompt }],
          ...(request.maxTokens ? { max_tokens: request.maxTokens } : {}),
          ...(request.temperature !== undefined ? { temperature: request.temperature } : {}),
        }),
      });
    } catch (error) {
      throw error instanceof Error ? error : new Error('OpenAI network error');
    }

    if (!response.ok) {
      throw new Error('OpenAI API error');
    }

    const data = (await response.json()) as { choices?: Array<{ message?: { content?: string; reasoning_content?: string } }>; usage?: { prompt_tokens?: number; completion_tokens?: number } };
    const message = data.choices?.[0]?.message;
    const text = message?.content?.trim() || message?.reasoning_content?.trim() || '';
    const usage: LLMUsage = { inputTokens: data.usage?.prompt_tokens, outputTokens: data.usage?.completion_tokens };
    return { text, usage };
  }
}

export function createOpenAILLMAdapterFromEnv(): LLMAdapter | null {
  const apiKey = process.env.OPENAI_API_KEY || process.env.OPENAI_KEY || process.env.ANTHROPIC_AUTH_TOKEN;
  if (!apiKey) return null;
  return new OpenAILLMAdapter({
    apiKey,
    baseUrl: process.env.OPENAI_BASE_URL || process.env.ANTHROPIC_BASE_URL || undefined,
    model: process.env.OPENAI_MODEL || undefined,
  });
}