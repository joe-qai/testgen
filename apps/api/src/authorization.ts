import { decodeAccessClaims, hasPermission, type PermissionCode, type AuthorizationContext } from '@testgen/auth';

export type AuthorizationOptions = {
  accessSecret: string;
  resolvePermissions: (userId: string) => Promise<ReadonlySet<PermissionCode>> | ReadonlySet<PermissionCode>;
  isPlatformAdmin?: (userId: string) => Promise<boolean> | boolean;
};

export type AuthorizedContext = AuthorizationContext & { hasPermission: (permission: PermissionCode) => boolean };

export function extractBearerToken(header: string | undefined): string | null {
  if (!header) return null;
  const match = /^Bearer\s+(.+)$/i.exec(header);
  return match ? match[1] : null;
}

export async function authorizeRequest(header: string | undefined, options: AuthorizationOptions): Promise<AuthorizedContext> {
  const token = extractBearerToken(header);
  if (!token) throw new Error('Unauthorized: missing Bearer token');

  let claims;
  try {
    claims = decodeAccessClaims(token, options.accessSecret);
  } catch {
    throw new Error('Unauthorized: invalid access token');
  }

  const platformAdmin = options.isPlatformAdmin ? await options.isPlatformAdmin(claims.sub) : Boolean(claims.isPlatformAdmin);
  const permissions = await options.resolvePermissions(claims.sub);
  const context: AuthorizationContext = { userId: claims.sub, organizationId: claims.organizationId, projectId: claims.projectId, isPlatformAdmin: platformAdmin, permissions };

  return {
    ...context,
    hasPermission: (permission: PermissionCode) => hasPermission(context, permission),
  };
}