import { Body, Controller, Get, Post } from '@nestjs/common';
import { createOpaqueToken, encodeAccessClaims } from '@testgen/auth';

@Controller('api/v1/auth')
export class AuthController {
  @Post('login')
  login(@Body() body: { email?: string }) {
    if (!body.email) return { data: null, error: { code: 'VALIDATION_ERROR', message: 'email is required' } };
    const userId = createOpaqueToken(16);
    const accessToken = encodeAccessClaims({ sub: userId, exp: Math.floor(Date.now() / 1000) + 900 }, process.env.JWT_ACCESS_SECRET ?? 'development-access-secret-please-change-32');
    return { data: { accessToken, refreshToken: createOpaqueToken(), user: { id: userId, email: body.email } }, meta: { requestId: createOpaqueToken(8) }, error: null };
  }

  @Get('me') me() { return { data: { authenticated: true }, meta: { requestId: createOpaqueToken(8) }, error: null }; }
}
