import { migrate } from 'drizzle-orm/node-postgres/migrator';
import { createDatabase, type Database } from './client.js';
import { rlsPolicySql } from './rls.sql.js';

export async function runMigrations(db: Database): Promise<void> {
  await migrate(db as never, { migrationsFolder: new URL('../migrations', import.meta.url).pathname });
  await db.execute(rlsPolicySql);
}

if (process.argv[1]?.endsWith('migrate.ts') || process.env.RUN_MIGRATE === 'true') {
  const { db, pool } = createDatabase();
  try {
    await runMigrations(db);
    console.log('Migrations applied and RLS policies enabled.');
  } finally {
    await pool.end();
  }
}