import { Pool } from 'pg';
import { drizzle } from 'drizzle-orm/node-postgres';
import * as schema from './schema.js';

export function createDatabase(connectionString = process.env.DATABASE_URL) {
  if (!connectionString) throw new Error('DATABASE_URL is required');
  const pool = new Pool({ connectionString });
  return { db: drizzle(pool, { schema }), pool };
}

export type Database = ReturnType<typeof createDatabase>['db'];
export type TenantContext = { userId: string; organizationId?: string; projectId?: string; isPlatformAdmin?: boolean };

export async function withTenantTransaction<T>(database: Database, context: TenantContext, callback: (tx: any) => Promise<T>): Promise<T> {
  return database.transaction(async (tx) => {
    await tx.execute({ queryChunks: [{ value: `select set_config('app.user_id', '${context.userId.replaceAll("'", "''")}', true)` }] } as any);
    if (context.organizationId) await tx.execute({ queryChunks: [{ value: `select set_config('app.organization_id', '${context.organizationId.replaceAll("'", "''")}', true)` }] } as any);
    if (context.projectId) await tx.execute({ queryChunks: [{ value: `select set_config('app.project_id', '${context.projectId.replaceAll("'", "''")}', true)` }] } as any);
    await tx.execute({ queryChunks: [{ value: `select set_config('app.is_platform_admin', '${context.isPlatformAdmin ? 'true' : 'false'}', true)` }] } as any);
    return callback(tx);
  });
}
