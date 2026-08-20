import { describe, expect, it } from 'vitest';
import { FeishuOAuthService } from './feishu-oauth.service.js';

function mockFetch(responder: (url: string, init: RequestInit) => Promise<{ ok: boolean; json: () => Promise<unknown> }>) {
  return (async (url: string | URL | Request, init?: RequestInit) => responder(String(url), init ?? {})) as unknown as typeof fetch;
}

const CONFIG = { appId: 'cli_abc123', appSecret: 'secret_xyz', redirectUri: 'http://localhost:3001/api/v1/auth/feishu/callback' };

describe('feishu oauth service', () => {
  it('builds an authorization URL with app_id, redirect_uri and state', () => {
    const service = new FeishuOAuthService(CONFIG, {} as typeof fetch);
    const url = service.buildAuthorizeUrl('state-123');
    expect(url).toContain('app_id=cli_abc123');
    expect(url).toContain(`redirect_uri=${encodeURIComponent(CONFIG.redirectUri)}`);
    expect(url).toContain('state=state-123');
  });

  it('exchanges a code for an access token and returns user info', async () => {
    let tokenUrl = '';
    let userUrl = '';
    let tokenHeaders: unknown = null;
    const fetchMock = mockFetch(async (url, init) => {
      if (url.includes('/oidc/access_token')) {
        tokenUrl = url;
        return { ok: true, json: async () => ({ access_token: 'feishu-at-123', refresh_token: 'feishu-rt-456', expires_in: 7200 }) };
      }
      if (url.includes('/user_info')) {
        userUrl = url;
        tokenHeaders = (init.headers as Record<string, string>).Authorization;
        return { ok: true, json: async () => ({ data: { open_id: 'ou_xxx', union_id: 'on_yyy', name: '张三', email: 'zhangsan@example.com' } }) };
      }
      throw new Error(`unexpected url ${url}`);
    });

    const service = new FeishuOAuthService(CONFIG, fetchMock);
    const result = await service.exchangeCode('code-123');

    expect(tokenUrl).toContain('/oidc/access_token');
    expect(result.accessToken).toBe('feishu-at-123');
    expect(userUrl).toContain('/user_info');
    expect(tokenHeaders).toBe('Bearer feishu-at-123');
    expect(result.user).toMatchObject({ openId: 'ou_xxx', name: '张三', email: 'zhangsan@example.com' });
  });

  it('throws when the token exchange fails', async () => {
    const fetchMock = mockFetch(async () => ({ ok: false, json: async () => ({}) }));
    const service = new FeishuOAuthService(CONFIG, fetchMock);
    await expect(service.exchangeCode('bad-code')).rejects.toThrow();
  });
});