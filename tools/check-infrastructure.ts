import { createClient } from 'redis';
import pg from 'pg';

const databaseUrl = process.env.DATABASE_URL ?? 'postgresql://testgen:testgen_dev_password@localhost:5433/testgen_platform';
const redisUrl = process.env.REDIS_URL ?? 'redis://localhost:6380';

const pool = new pg.Pool({ connectionString: databaseUrl, max: 1 });
const redis = createClient({ url: redisUrl });

try {
  await pool.query('SELECT 1');
  await redis.connect();
  const response = await redis.ping();
  if (response !== 'PONG') throw new Error(`Unexpected Redis response: ${response}`);
  console.log('PostgreSQL: OK');
  console.log('Redis: OK');
} finally {
  await redis.quit().catch(() => undefined);
  await pool.end();
}
