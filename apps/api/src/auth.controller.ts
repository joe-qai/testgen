import { Body, Controller, Get, Post } from '@nestjs/common';
import { AuthService } from './auth.service.js';

@Controller('api/v1/auth')
export class AuthController {
  constructor(private readonly authService: AuthService) {}

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
}