import argon2 from 'argon2';
import { createOpaqueToken, encodeAccessClaims, hashToken } from '@testgen/auth';

export type LocalUser = { id: string; email: string; displayName: string; passwordHash: string; status: 'ACTIVE' | 'DISABLED' };
export type LoginResult = { accessToken: string; refreshToken: string; user: Omit<LocalUser, 'passwordHash'> };

export class AuthService {
  private readonly users = new Map<string, LocalUser>();
  private readonly refreshes = new Set<string>();
  constructor(private readonly accessSecret: string, private readonly refreshSecret: string) {}
  async createUser(input: { email: string; password: string; displayName: string }) { const user: LocalUser = { id: crypto.randomUUID(), email: input.email, displayName: input.displayName, passwordHash: await argon2.hash(input.password), status: 'ACTIVE' }; this.users.set(input.email.toLowerCase(), user); return user; }
  async login(email: string, password: string): Promise<LoginResult> { const user = this.users.get(email.toLowerCase()); if (!user || user.status !== 'ACTIVE' || !(await argon2.verify(user.passwordHash, password))) throw new Error('Invalid credentials'); const refreshToken = createOpaqueToken(); this.refreshes.add(hashToken(refreshToken, this.refreshSecret)); const accessToken = encodeAccessClaims({ sub: user.id, exp: Math.floor(Date.now() / 1000) + 900 }, this.accessSecret); const { passwordHash: _, ...safeUser } = user; return { accessToken, refreshToken, user: safeUser }; }
  revoke(refreshToken: string) { this.refreshes.delete(hashToken(refreshToken, this.refreshSecret)); }
}
