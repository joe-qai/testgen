export type FeishuOAuthConfig = {
  appId: string;
  appSecret: string;
  redirectUri: string;
};

export type FeishuUserInfo = {
  openId: string;
  unionId?: string;
  name: string;
  email?: string;
  avatarUrl?: string;
};

export type FeishuOAuthResult = {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  user: FeishuUserInfo;
};

const AUTHORIZE_BASE = 'https://open.feishu.cn/open-apis/authen/v1/authorize';
const TOKEN_ENDPOINT = 'https://open.feishu.cn/open-apis/authen/v1/oidc/access_token';
const USERINFO_ENDPOINT = 'https://open.feishu.cn/open-apis/authen/v1/user_info';

export class FeishuOAuthService {
  constructor(private readonly config: FeishuOAuthConfig, private readonly fetchImpl: typeof fetch = globalThis.fetch) {}

  buildAuthorizeUrl(state: string): string {
    const params = new URLSearchParams({
      app_id: this.config.appId,
      redirect_uri: this.config.redirectUri,
      state,
    });
    return `${AUTHORIZE_BASE}?${params.toString()}`;
  }

  private async exchangeCodeForToken(code: string): Promise<{ accessToken: string; refreshToken: string; expiresIn: number }> {
    const response = await this.fetchImpl(TOKEN_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        grant_type: 'authorization_code',
        code,
        client_id: this.config.appId,
        client_secret: this.config.appSecret,
      }),
    });
    if (!response.ok) throw new Error('Feishu token exchange failed');
    const data = (await response.json()) as { access_token?: string; refresh_token?: string; expires_in?: number };
    if (!data.access_token) throw new Error('Feishu token exchange failed');
    return { accessToken: data.access_token, refreshToken: data.refresh_token ?? '', expiresIn: data.expires_in ?? 7200 };
  }

  private async fetchUserInfo(accessToken: string): Promise<FeishuUserInfo> {
    const response = await this.fetchImpl(USERINFO_ENDPOINT, { headers: { Authorization: `Bearer ${accessToken}` } });
    if (!response.ok) throw new Error('Feishu user info failed');
    const data = (await response.json()) as { data?: { open_id?: string; union_id?: string; name?: string; email?: string; avatar_url?: string } };
    const info = data.data;
    if (!info?.open_id) throw new Error('Feishu user info failed');
    return { openId: info.open_id, unionId: info.union_id, name: info.name ?? '', email: info.email, avatarUrl: info.avatar_url };
  }

  async exchangeCode(code: string): Promise<FeishuOAuthResult> {
    const token = await this.exchangeCodeForToken(code);
    const user = await this.fetchUserInfo(token.accessToken);
    return { ...token, user };
  }
}