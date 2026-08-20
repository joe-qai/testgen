import { createDatabase, type Database } from './client.js';
import { organizations, roles, permissions, rolePermissions, users, organizationMembers, organizationMemberRoles, userPlatformRoles } from './schema.js';
import { eq, and } from 'drizzle-orm';

const adminEmail = process.env.BOOTSTRAP_ADMIN_EMAIL ?? 'admin@example.com';
const adminName = process.env.BOOTSTRAP_ADMIN_NAME ?? '平台管理员';
const organizationName = process.env.BOOTSTRAP_ADMIN_ORGANIZATION_NAME ?? '默认组织';

const permissionSeeds = [
  ['organization:read', 'organization', 'read'],
  ['organization:manage_members', 'organization', 'manage_members'],
  ['project:create', 'project', 'create'],
  ['project:read', 'project', 'read'],
  ['project:update', 'project', 'update'],
  ['project:archive', 'project', 'archive'],
  ['project:manage_members', 'project', 'manage_members'],
  ['workflow_run:create', 'workflow_run', 'create'],
  ['workflow_run:read', 'workflow_run', 'read'],
  ['workflow_run:cancel', 'workflow_run', 'cancel'],
  ['audit_log:read', 'audit_log', 'read'],
] as const;

export async function runSeed(db: Database): Promise<{ adminEmail: string; organizationName: string }> {
  const [admin] = await db.insert(users).values({ email: adminEmail, displayName: adminName }).onConflictDoUpdate({ target: users.email, set: { displayName: adminName } }).returning();
  const slug = organizationName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'default-org';
  const [organization] = await db.insert(organizations).values({ name: organizationName, slug, createdBy: admin.id }).onConflictDoUpdate({ target: organizations.slug, set: { name: organizationName } }).returning();
  const [member] = await db.insert(organizationMembers).values({ organizationId: organization.id, userId: admin.id }).onConflictDoNothing().returning();
  const memberId = member?.id ?? (await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, organization.id), eq(organizationMembers.userId, admin.id))).limit(1))[0].id;
  const permissionRows = [];
  for (const [code, resource, action] of permissionSeeds) permissionRows.push((await db.insert(permissions).values({ code, resource, action }).onConflictDoUpdate({ target: permissions.code, set: { resource, action } }).returning())[0]);
  const [platformRole] = await db.insert(roles).values({ scope: 'PLATFORM', code: 'platform_admin', name: '平台管理员' }).onConflictDoUpdate({ target: roles.code, set: { name: '平台管理员' } }).returning();
  const [organizationRole] = await db.insert(roles).values({ scope: 'ORGANIZATION', code: 'organization_admin', name: '组织管理员' }).onConflictDoUpdate({ target: roles.code, set: { name: '组织管理员' } }).returning();
  for (const permission of permissionRows) await db.insert(rolePermissions).values({ roleId: platformRole.id, permissionId: permission.id }).onConflictDoNothing();
  for (const permission of permissionRows.filter((item) => item.code !== 'audit_log:read')) await db.insert(rolePermissions).values({ roleId: organizationRole.id, permissionId: permission.id }).onConflictDoNothing();
  await db.insert(userPlatformRoles).values({ userId: admin.id, roleId: platformRole.id }).onConflictDoNothing();
  await db.insert(organizationMemberRoles).values({ organizationMemberId: memberId, roleId: organizationRole.id }).onConflictDoNothing();
  return { adminEmail: admin.email, organizationName: organization.name };
}

if (process.argv[1]?.endsWith('seed.ts') || process.env.RUN_SEED === 'true') {
  const { db, pool } = createDatabase();
  try {
    const result = await runSeed(db);
    console.log(`Bootstrap seed ready: ${result.adminEmail} / ${result.organizationName}`);
  } finally {
    await pool.end();
  }
}