import { describe, expect, it } from 'vitest';
import { AuthService } from './auth.service.js';
import { decodeAccessClaims } from '@testgen/auth';

describe('auth service', () => {
  it('logs in a bootstrap user with a valid password', async () => {
    const service = new AuthService('access-secret-123456789012345678901234', 'refresh-secret-123456789012345678901234');
    await service.createUser({ email: 'admin@example.com', password: 'Correct#123', displayName: 'Admin' });
    const result = await service.login('admin@example.com', 'Correct#123');
    expect(result.accessToken).toContain('.');
    expect(result.refreshToken).toBeTruthy();
    expect(result.user).not.toHaveProperty('passwordHash');
  });

  it('rejects an invalid password', async () => {
    const service = new AuthService('access-secret-123456789012345678901234', 'refresh-secret-123456789012345678901234');
    await service.createUser({ email: 'admin@example.com', password: 'Correct#123', displayName: 'Admin' });
    await expect(service.login('admin@example.com', 'wrong')).rejects.toThrow('Invalid credentials');
  });

  it('rotates a refresh token to a new pair and invalidates the old one', async () => {
    const service = new AuthService('access-secret-123456789012345678901234', 'refresh-secret-123456789012345678901234');
    await service.createUser({ email: 'user@example.com', password: 'Right#456', displayName: 'User' });
    const login = await service.login('user@example.com', 'Right#456');
    const rotated = await service.refresh(login.refreshToken);
    expect(rotated.accessToken).toContain('.');
    expect(rotated.refreshToken).not.toBe(login.refreshToken);
    expect(decodeAccessClaims(rotated.accessToken, 'access-secret-123456789012345678901234').sub).toBe(login.user.id);
    await expect(service.refresh(login.refreshToken)).rejects.toThrow('Invalid refresh token');
  });

  it('emits an access token that is verifiable', async () => {
    const service = new AuthService('access-secret-123456789012345678901234', 'refresh-secret-123456789012345678901234');
    await service.createUser({ email: 'v@example.com', password: 'Pass#999', displayName: 'V' });
    const result = await service.login('v@example.com', 'Pass#999');
    const claims = decodeAccessClaims(result.accessToken, 'access-secret-123456789012345678901234');
    expect(claims.sub).toBe(result.user.id);
    expect(claims.exp).toBeGreaterThan(Math.floor(Date.now() / 1000));
  });

  it('issues tokens for an external (feishu) user idempotently by external id', async () => {
    const service = new AuthService('access-secret-123456789012345678901234', 'refresh-secret-123456789012345678901234');
    const first = await service.issueTokensForExternalUser({ externalId: 'ou_abc', name: '张三', email: 'zhangsan@example.com' });
    const second = await service.issueTokensForExternalUser({ externalId: 'ou_abc', name: '张三', email: 'zhangsan@example.com' });
    expect(first.user.id).toBe(second.user.id);
    expect(first.user.email).toContain('ou_abc');
    expect(first.accessToken).toContain('.');
    // 该用户不需要密码即可获得 token，且 refresh 可用
    const rotated = await service.refresh(first.refreshToken);
    expect(rotated.user.id).toBe(first.user.id);
  });
});