import { z } from 'zod';

const EnvSchema = z.object({
  NODE_ENV: z.enum(['development','test','production']).default('development'),
  DATABASE_URL: z.string().min(1),
  REDIS_URL: z.string().min(1),
  JWT_ACCESS_SECRET: z.string().min(32),
  JWT_REFRESH_SECRET: z.string().min(32),
  BOOTSTRAP_ADMIN_EMAIL: z.string().email(),
  BOOTSTRAP_ADMIN_NAME: z.string().min(1),
  BOOTSTRAP_ADMIN_ORGANIZATION_NAME: z.string().min(1),
  FEISHU_ENABLED: z.coerce.boolean().default(false),
  FEISHU_APP_ID: z.string().optional(),
  FEISHU_APP_SECRET: z.string().optional(),
  QUEUE_PROVIDER: z.enum(['bullmq','platform']).default('bullmq'),
  STORAGE_PROVIDER: z.enum(['local','dataloom']).default('local'),
});
export type AppConfig = z.infer<typeof EnvSchema>;
export function loadConfig(env: Record<string, unknown>): AppConfig { const parsed=EnvSchema.parse(env); if(parsed.FEISHU_ENABLED && (!parsed.FEISHU_APP_ID || !parsed.FEISHU_APP_SECRET)) throw new Error('Feishu credentials are required when enabled'); return parsed; }
