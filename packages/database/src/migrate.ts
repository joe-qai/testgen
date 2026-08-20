import { sql } from 'drizzle-orm';
import { createDatabase } from './client.js';

const { db, pool } = createDatabase();

try {
  await db.execute(sql`
    create or replace function app_user_id() returns uuid language sql stable as $$
      select nullif(current_setting('app.user_id', true), '')::uuid
    $$;
    create or replace function app_organization_id() returns uuid language sql stable as $$
      select nullif(current_setting('app.organization_id', true), '')::uuid
    $$;
    create or replace function app_is_platform_admin() returns boolean language sql stable as $$
      select coalesce(current_setting('app.is_platform_admin', true), 'false') = 'true'
    $$;
  `);
  console.log('RLS helper functions installed. Run drizzle migrations before enabling table policies.');
} finally {
  await pool.end();
}
