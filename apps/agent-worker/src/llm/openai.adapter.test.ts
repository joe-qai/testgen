import { describe, expect, it } from 'vitest';
import { OpenAILLMAdapter } from './openai.adapter.js';

function mockFetch(handler: (url: string, init: RequestInit) => Promise<{ ok: boolean; json: () => Promise<unknown> }>) {
  return (async (url: string | URL | Request, init?: RequestInit) => handler(String(url), init ?? {})) as unknown as typeof fetch;
}

describe('openai llm adapter', () => {
  it('posts a chat completion request and returns text with usage', async () => {
    let capturedUrl = '';
    let capturedBody: unknown = null;
    let capturedHeaders: unknown = null;
    const fetchMock = mockFetch(async (url, init) => {
      capturedUrl = url;
      capturedBody = JSON.parse(String(init.body));
      capturedHeaders = init.headers;
      return { ok: true, json: async () => ({ choices: [{ message: { content: '真实生成的测试要点' } }], usage: { prompt_tokens: 12, completion_tokens: 5 } }) };
    });

    const adapter = new OpenAILLMAdapter({ apiKey: 'sk-test', baseUrl: 'https://api.example.com', model: 'gpt-4o-mini', fetch: fetchMock });
    const result = await adapter.complete({ prompt: '分析需求', maxTokens: 200, temperature: 0.3 });

    expect(capturedUrl).toBe('https://api.example.com/chat/completions');
    expect(capturedHeaders).toMatchObject({ Authorization: 'Bearer sk-test', 'Content-Type': 'application/json' });
    expect(capturedBody).toMatchObject({ model: 'gpt-4o-mini', max_tokens: 200, temperature: 0.3 });
    expect((capturedBody as { messages: Array<{ role: string }> }).messages).toEqual([{ role: 'user', content: '分析需求' }]);
    expect(result.text).toBe('真实生成的测试要点');
    expect(result.usage).toEqual({ inputTokens: 12, outputTokens: 5 });
  });

  it('defaults base URL and model when not provided', async () => {
    const fetchMock = mockFetch(async () => ({ ok: true, json: async () => ({ choices: [{ message: { content: 'x' } }], usage: {} }) }));
    const adapter = new OpenAILLMAdapter({ apiKey: 'sk-test', fetch: fetchMock });
    await adapter.complete({ prompt: 'hi' });
  });

  it('blocks non-ok responses without leaking the body', async () => {
    const fetchMock = mockFetch(async () => ({ ok: false, json: async () => ({ error: { message: 'invalid api key' } }) }));
    const adapter = new OpenAILLMAdapter({ apiKey: 'sk-test', fetch: fetchMock });
    await expect(adapter.complete({ prompt: 'hi' })).rejects.toThrow('OpenAI API error');
  });

  it('throws on network failure', async () => {
    const fetchMock = mockFetch(async () => { throw new Error('network down'); });
    const adapter = new OpenAILLMAdapter({ apiKey: 'sk-test', fetch: fetchMock });
    await expect(adapter.complete({ prompt: 'hi' })).rejects.toThrow('network down');
  });
});