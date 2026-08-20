import { describe, expect, it } from 'vitest';
import { AuthService } from './auth.service.js';

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
});
