import { createHmac, randomBytes } from 'node:crypto';

export type AccessClaims = { sub: string; organizationId?: string; isPlatformAdmin?: boolean; exp: number };

export function hashToken(token: string, secret: string): string {
  return createHmac('sha256', secret).update(token).digest('hex');
}

export function createOpaqueToken(bytes = 32): string {
  return randomBytes(bytes).toString('base64url');
}

export function encodeAccessClaims(claims: AccessClaims, secret: string): string {
  const payload = Buffer.from(JSON.stringify(claims)).toString('base64url');
  const signature = hashToken(payload, secret);
  return `${payload}.${signature}`;
}

export function decodeAccessClaims(token: string, secret: string): AccessClaims {
  const [payload, signature] = token.split('.');
  if (!payload || !signature || hashToken(payload, secret) !== signature) throw new Error('Invalid access token');
  const claims = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as AccessClaims;
  if (claims.exp <= Math.floor(Date.now() / 1000)) throw new Error('Access token expired');
  return claims;
}
