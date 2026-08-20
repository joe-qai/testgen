import { Body, Controller, Get, Optional, Post, Query, Res } from '@nestjs/common';
import { AuthService } from './auth.service.js';
import { FeishuOAuthService } from './feishu-oauth.service.js';

type RedirectResponse = { redirect(url: string): void; status(code: number): { json(body: unknown): void } };

@Controller('api/v1/auth')
export class AuthController {
  constructor(private readonly authService: AuthService, @Optional() private readonly feishuOAuth?: FeishuOAuthService) {}

  @Post('login')
  async login(@Body() body: { email?: string; password?: string }) {
    if (!body.email || !body.password) return { data: null, meta: {}, error: { code: 'VALIDATION_ERROR', message: 'email and password are required' } };
    try {
      const result = await this.authService.login(body.email, body.password);
      return { data: result, meta: {}, error: null };
    } catch (error) {
      return { data: null, meta: {}, error: { code: 'INVALID_CREDENTIALS', message: error instanceof Error ? error.message : 'Login failed' } };
    }
  }

  @Post('refresh')
  async refresh(@Body() body: { refreshToken?: string }) {
    if (!body.refreshToken) return { data: null, meta: {}, error: { code: 'VALIDATION_ERROR', message: 'refreshToken is required' } };
    try {
      const result = await this.authService.refresh(body.refreshToken);
      return { data: result, meta: {}, error: null };
    } catch {
      return { data: null, meta: {}, error: { code: 'INVALID_REFRESH_TOKEN', message: 'Invalid refresh token' } };
    }
  }

  @Get('me')
  me() {
    return { data: { authenticated: true }, meta: {}, error: null };
  }

  @Get('feishu')
  feishuRedirect(@Res() response: RedirectResponse) {
    if (!this.feishuOAuth) return response.status(503).json({ data: null, meta: {}, error: { code: 'FEISHU_NOT_CONFIGURED', message: '飞书登录未配置' } });
    const state = Math.random().toString(36).slice(2, 14);
    response.redirect(this.feishuOAuth.buildAuthorizeUrl(state));
  }

  @Get('feishu/callback')
  async feishuCallback(@Query('code') code: string | undefined, @Res() response: RedirectResponse) {
    if (!this.feishuOAuth || !code) return response.status(400).json({ data: null, meta: {}, error: { code: 'FEISHU_CALLBACK_ERROR', message: '缺少 code 或飞书未配置' } });
    try {
      const result = await this.feishuOAuth.exchangeCode(code);
      const logged = await this.authService.issueTokensForExternalUser({ externalId: result.user.openId, name: result.user.name, email: result.user.email });
      response.redirect(`http://localhost:5173/feishu-callback?accessToken=${encodeURIComponent(logged.accessToken)}&refreshToken=${encodeURIComponent(logged.refreshToken)}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : '飞书登录失败';
      return response.status(502).json({ data: null, meta: {}, error: { code: 'FEISHU_LOGIN_FAILED', message } });
    }
  }
}