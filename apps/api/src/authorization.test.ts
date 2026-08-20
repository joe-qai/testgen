import { describe, expect, it } from 'vitest';
import { encodeAccessClaims } from '@testgen/auth';
import { authorizeRequest } from './authorization.js';

const SECRET = 'access-secret-123456789012345678901234';

function validToken(userId = 'user-1', isPlatformAdmin = false) {
  return encodeAccessClaims({ sub: userId, isPlatformAdmin, exp: Math.floor(Date.now() / 1000) + 900 }, SECRET);
}

describe('authorization', () => {
  it('resolves an authorization context from a valid Bearer token', async () => {
    const context = await authorizeRequest(`Bearer ${validToken('u-1')}`, {
      accessSecret: SECRET,
      resolvePermissions: async (userId) => new Set([`${userId}:read` as `${string}:${string}`]),
    });
    expect(context.userId).toBe('u-1');
    expect(context.hasPermission('u-1:read' as `${string}:${string}`)).toBe(true);
    expect(context.hasPermission('u-1:write' as `${string}:${string}`)).toBe(false);
  });

  it('rejects a missing Authorization header', async () => {
    await expect(authorizeRequest(undefined, { accessSecret: SECRET, resolvePermissions: () => new Set() })).rejects.toThrow('Unauthorized');
  });

  it('rejects a malformed token', async () => {
    await expect(authorizeRequest('Bearer not-a-token', { accessSecret: SECRET, resolvePermissions: () => new Set() })).rejects.toThrow();
  });

  it('rejects a token with wrong secret', async () => {
    const token = encodeAccessClaims({ sub: 'u-1', exp: Math.floor(Date.now() / 1000) + 900 }, 'other-secret-123456789012345678901234');
    await expect(authorizeRequest(`Bearer ${token}`, { accessSecret: SECRET, resolvePermissions: () => new Set() })).rejects.toThrow();
  });

  it('grants all permissions to a platform admin', async () => {
    const context = await authorizeRequest(`Bearer ${validToken('u-2', true)}`, {
      accessSecret: SECRET,
      resolvePermissions: async () => new Set(),
    });
    expect(context.hasPermission('any:thing' as `${string}:${string}`)).toBe(true);
  });
});