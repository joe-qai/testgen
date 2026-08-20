import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from '@nestjs/common';
import { authorizeRequest, type AuthorizedContext, type AuthorizationOptions } from './authorization.js';

export type AuthGuardOptions = AuthorizationOptions & { publicRoutes?: string[] };

@Injectable()
export class JwtAuthGuard implements CanActivate {
  constructor(private readonly options: AuthGuardOptions) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest<{ headers: Record<string, string | undefined>; user?: AuthorizedContext }>();
    const header = request.headers?.['authorization'];

    try {
      request.user = await authorizeRequest(header, this.options);
      return true;
    } catch (error) {
      throw new UnauthorizedException(error instanceof Error ? error.message : 'Unauthorized');
    }
  }
}