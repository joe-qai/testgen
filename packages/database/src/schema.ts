import { pgTable, uuid, varchar, text, timestamp, boolean, jsonb, integer, uniqueIndex, index } from 'drizzle-orm/pg-core';

const timestamps = {
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).defaultNow().notNull(),
};

export const users = pgTable('users', {
  id: uuid('id').defaultRandom().primaryKey(),
  email: varchar('email', { length: 320 }).notNull().unique(),
  displayName: varchar('display_name', { length: 200 }).notNull(),
  avatarUrl: text('avatar_url'),
  passwordHash: text('password_hash'),
  status: varchar('status', { length: 30 }).notNull().default('ACTIVE'),
  passwordUpdatedAt: timestamp('password_updated_at', { withTimezone: true }),
  lastLoginAt: timestamp('last_login_at', { withTimezone: true }),
  deletedAt: timestamp('deleted_at', { withTimezone: true }),
  ...timestamps,
});

export const userIdentities = pgTable('user_identities', {
  id: uuid('id').defaultRandom().primaryKey(),
  userId: uuid('user_id').notNull().references(() => users.id),
  provider: varchar('provider', { length: 30 }).notNull(),
  providerUserId: varchar('provider_user_id', { length: 200 }).notNull(),
  providerTenantKey: varchar('provider_tenant_key', { length: 200 }),
  providerOpenId: varchar('provider_open_id', { length: 200 }),
  providerUnionId: varchar('provider_union_id', { length: 200 }),
  profileSnapshot: jsonb('profile_snapshot'),
  ...timestamps,
}, (table) => ({ identityUnique: uniqueIndex('user_identity_provider_unique').on(table.provider, table.providerUserId, table.providerTenantKey) }));

export const refreshTokens = pgTable('refresh_tokens', {
  id: uuid('id').defaultRandom().primaryKey(),
  userId: uuid('user_id').notNull().references(() => users.id),
  tokenHash: text('token_hash').notNull().unique(),
  deviceId: varchar('device_id', { length: 200 }),
  userAgent: text('user_agent'),
  ipAddress: varchar('ip_address', { length: 100 }),
  expiresAt: timestamp('expires_at', { withTimezone: true }).notNull(),
  revokedAt: timestamp('revoked_at', { withTimezone: true }),
  lastUsedAt: timestamp('last_used_at', { withTimezone: true }),
  ...timestamps,
});

export const organizations = pgTable('organizations', {
  id: uuid('id').defaultRandom().primaryKey(),
  name: varchar('name', { length: 200 }).notNull(),
  slug: varchar('slug', { length: 100 }).notNull().unique(),
  status: varchar('status', { length: 30 }).notNull().default('ACTIVE'),
  logoUrl: text('logo_url'),
  settings: jsonb('settings'),
  createdBy: uuid('created_by'),
  deletedAt: timestamp('deleted_at', { withTimezone: true }),
  ...timestamps,
});

export const organizationMembers = pgTable('organization_members', {
  id: uuid('id').defaultRandom().primaryKey(),
  organizationId: uuid('organization_id').notNull().references(() => organizations.id),
  userId: uuid('user_id').notNull().references(() => users.id),
  status: varchar('status', { length: 30 }).notNull().default('ACTIVE'),
  joinedAt: timestamp('joined_at', { withTimezone: true }).defaultNow().notNull(),
  invitedBy: uuid('invited_by'),
  ...timestamps,
}, (table) => ({ memberUnique: uniqueIndex('organization_member_unique').on(table.organizationId, table.userId), orgIndex: index('organization_member_org_idx').on(table.organizationId) }));

export const feishuTenants = pgTable('feishu_tenants', {
  id: uuid('id').defaultRandom().primaryKey(),
  organizationId: uuid('organization_id').notNull().references(() => organizations.id),
  tenantKey: varchar('tenant_key', { length: 200 }).notNull().unique(),
  tenantName: varchar('tenant_name', { length: 200 }).notNull(),
  status: varchar('status', { length: 30 }).notNull().default('ACTIVE'),
  profileSnapshot: jsonb('profile_snapshot'),
  ...timestamps,
});

export const roles = pgTable('roles', {
  id: uuid('id').defaultRandom().primaryKey(),
  scope: varchar('scope', { length: 30 }).notNull(),
  code: varchar('code', { length: 100 }).notNull().unique(),
  name: varchar('name', { length: 100 }).notNull(),
  description: text('description'),
  isSystem: boolean('is_system').notNull().default(true),
  organizationId: uuid('organization_id').references(() => organizations.id),
  ...timestamps,
});

export const permissions = pgTable('permissions', {
  id: uuid('id').defaultRandom().primaryKey(),
  code: varchar('code', { length: 150 }).notNull().unique(),
  resource: varchar('resource', { length: 100 }).notNull(),
  action: varchar('action', { length: 100 }).notNull(),
  description: text('description'),
});

export const rolePermissions = pgTable('role_permissions', {
  roleId: uuid('role_id').notNull().references(() => roles.id),
  permissionId: uuid('permission_id').notNull().references(() => permissions.id),
}, (table) => ({ rolePermissionUnique: uniqueIndex('role_permission_unique').on(table.roleId, table.permissionId) }));

export const userPlatformRoles = pgTable('user_platform_roles', {
  userId: uuid('user_id').notNull().references(() => users.id),
  roleId: uuid('role_id').notNull().references(() => roles.id),
  assignedBy: uuid('assigned_by'),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
}, (table) => ({ userRoleUnique: uniqueIndex('user_platform_role_unique').on(table.userId, table.roleId) }));

export const organizationMemberRoles = pgTable('organization_member_roles', {
  organizationMemberId: uuid('organization_member_id').notNull().references(() => organizationMembers.id),
  roleId: uuid('role_id').notNull().references(() => roles.id),
  assignedBy: uuid('assigned_by'),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
}, (table) => ({ memberRoleUnique: uniqueIndex('organization_member_role_unique').on(table.organizationMemberId, table.roleId) }));

export const projects = pgTable('projects', {
  id: uuid('id').defaultRandom().primaryKey(),
  organizationId: uuid('organization_id').notNull().references(() => organizations.id),
  key: varchar('key', { length: 50 }).notNull(),
  name: varchar('name', { length: 200 }).notNull(),
  description: text('description'),
  status: varchar('status', { length: 30 }).notNull().default('ACTIVE'),
  ownerId: uuid('owner_id').notNull().references(() => users.id),
  settings: jsonb('settings'),
  createdBy: uuid('created_by').notNull().references(() => users.id),
  updatedBy: uuid('updated_by').notNull().references(() => users.id),
  archivedAt: timestamp('archived_at', { withTimezone: true }),
  ...timestamps,
}, (table) => ({ orgKeyUnique: uniqueIndex('project_org_key_unique').on(table.organizationId, table.key), orgStatusIndex: index('project_org_status_idx').on(table.organizationId, table.status) }));

export const projectMembers = pgTable('project_members', {
  id: uuid('id').defaultRandom().primaryKey(),
  organizationId: uuid('organization_id').notNull().references(() => organizations.id),
  projectId: uuid('project_id').notNull().references(() => projects.id),
  userId: uuid('user_id').notNull().references(() => users.id),
  status: varchar('status', { length: 30 }).notNull().default('ACTIVE'),
  joinedAt: timestamp('joined_at', { withTimezone: true }).defaultNow().notNull(),
  invitedBy: uuid('invited_by'),
  ...timestamps,
}, (table) => ({ projectMemberUnique: uniqueIndex('project_member_unique').on(table.projectId, table.userId), projectIndex: index('project_member_project_idx').on(table.organizationId, table.projectId) }));

export const projectMemberRoles = pgTable('project_member_roles', {
  projectMemberId: uuid('project_member_id').notNull().references(() => projectMembers.id),
  roleId: uuid('role_id').notNull().references(() => roles.id),
  assignedBy: uuid('assigned_by'),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
}, (table) => ({ projectRoleUnique: uniqueIndex('project_member_role_unique').on(table.projectMemberId, table.roleId) }));

export const workflowDefinitions = pgTable('workflow_definitions', {
  id: uuid('id').defaultRandom().primaryKey(),
  organizationId: uuid('organization_id').references(() => organizations.id),
  code: varchar('code', { length: 100 }).notNull(),
  name: varchar('name', { length: 200 }).notNull(),
  description: text('description'),
  scope: varchar('scope', { length: 30 }).notNull().default('PLATFORM'),
  status: varchar('status', { length: 30 }).notNull().default('ACTIVE'),
  createdBy: uuid('created_by').references(() => users.id),
  ...timestamps,
}, (table) => ({ workflowCodeIndex: uniqueIndex('workflow_definition_scope_code_unique').on(table.organizationId, table.code) }));

export const workflowVersions = pgTable('workflow_versions', {
  id: uuid('id').defaultRandom().primaryKey(),
  workflowDefinitionId: uuid('workflow_definition_id').notNull().references(() => workflowDefinitions.id),
  version: integer('version').notNull(),
  graphDefinition: jsonb('graph_definition').notNull(),
  inputSchema: jsonb('input_schema').notNull(),
  outputSchema: jsonb('output_schema').notNull(),
  status: varchar('status', { length: 30 }).notNull().default('DRAFT'),
  publishedAt: timestamp('published_at', { withTimezone: true }),
  createdBy: uuid('created_by').references(() => users.id),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
}, (table) => ({ workflowVersionUnique: uniqueIndex('workflow_version_unique').on(table.workflowDefinitionId, table.version) }));

export const workflowRuns = pgTable('workflow_runs', {
  id: uuid('id').defaultRandom().primaryKey(),
  organizationId: uuid('organization_id').notNull().references(() => organizations.id),
  projectId: uuid('project_id').notNull().references(() => projects.id),
  workflowDefinitionId: uuid('workflow_definition_id').references(() => workflowDefinitions.id),
  workflowVersionId: uuid('workflow_version_id').references(() => workflowVersions.id),
  workflowCode: varchar('workflow_code', { length: 100 }),
  requestedBy: uuid('requested_by').notNull().references(() => users.id),
  status: varchar('status', { length: 30 }).notNull().default('CREATED'),
  inputData: jsonb('input_data').notNull(),
  outputData: jsonb('output_data'),
  errorData: jsonb('error_data'),
  currentNode: varchar('current_node', { length: 100 }),
  progress: integer('progress').notNull().default(0),
  idempotencyKey: varchar('idempotency_key', { length: 200 }).notNull(),
  queuedAt: timestamp('queued_at', { withTimezone: true }),
  startedAt: timestamp('started_at', { withTimezone: true }),
  completedAt: timestamp('completed_at', { withTimezone: true }),
  ...timestamps,
}, (table) => ({ runIdempotencyUnique: uniqueIndex('workflow_run_idempotency_unique').on(table.organizationId, table.requestedBy, table.idempotencyKey), runProjectIndex: index('workflow_run_project_idx').on(table.organizationId, table.projectId, table.createdAt) }));

export const workflowNodeRuns = pgTable('workflow_node_runs', {
  id: uuid('id').defaultRandom().primaryKey(),
  workflowRunId: uuid('workflow_run_id').notNull().references(() => workflowRuns.id),
  organizationId: uuid('organization_id').notNull().references(() => organizations.id),
  projectId: uuid('project_id').notNull().references(() => projects.id),
  nodeName: varchar('node_name', { length: 100 }).notNull(),
  nodeType: varchar('node_type', { length: 50 }).notNull(),
  status: varchar('status', { length: 30 }).notNull().default('RUNNING'),
  inputData: jsonb('input_data'),
  outputData: jsonb('output_data'),
  errorData: jsonb('error_data'),
  attempt: integer('attempt').notNull().default(1),
  startedAt: timestamp('started_at', { withTimezone: true }).defaultNow().notNull(),
  completedAt: timestamp('completed_at', { withTimezone: true }),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
});

export const workflowEvents = pgTable('workflow_events', {
  id: uuid('id').defaultRandom().primaryKey(),
  workflowRunId: uuid('workflow_run_id').notNull().references(() => workflowRuns.id),
  organizationId: uuid('organization_id').notNull().references(() => organizations.id),
  projectId: uuid('project_id').notNull().references(() => projects.id),
  sequence: integer('sequence').notNull(),
  eventType: varchar('event_type', { length: 50 }).notNull(),
  nodeName: varchar('node_name', { length: 100 }),
  payload: jsonb('payload').notNull(),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
}, (table) => ({ eventSequenceUnique: uniqueIndex('workflow_event_sequence_unique').on(table.workflowRunId, table.sequence), runEventIndex: index('workflow_event_run_idx').on(table.workflowRunId, table.sequence) }));

export const workflowInterrupts = pgTable('workflow_interrupts', {
  id: uuid('id').defaultRandom().primaryKey(),
  workflowRunId: uuid('workflow_run_id').notNull().references(() => workflowRuns.id),
  organizationId: uuid('organization_id').notNull().references(() => organizations.id),
  projectId: uuid('project_id').notNull().references(() => projects.id),
  nodeName: varchar('node_name', { length: 100 }).notNull(),
  reason: text('reason').notNull(),
  interruptData: jsonb('interrupt_data'),
  status: varchar('status', { length: 30 }).notNull().default('PENDING'),
  resumedBy: uuid('resumed_by').references(() => users.id),
  resumedData: jsonb('resumed_data'),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
  resumedAt: timestamp('resumed_at', { withTimezone: true }),
  expiresAt: timestamp('expires_at', { withTimezone: true }),
});

export const auditLogs = pgTable('audit_logs', {
  id: uuid('id').defaultRandom().primaryKey(),
  organizationId: uuid('organization_id').references(() => organizations.id),
  projectId: uuid('project_id').references(() => projects.id),
  actorUserId: uuid('actor_user_id').references(() => users.id),
  action: varchar('action', { length: 150 }).notNull(),
  resourceType: varchar('resource_type', { length: 100 }).notNull(),
  resourceId: uuid('resource_id'),
  requestId: varchar('request_id', { length: 100 }),
  ipAddress: varchar('ip_address', { length: 100 }),
  userAgent: text('user_agent'),
  metadata: jsonb('metadata'),
  createdAt: timestamp('created_at', { withTimezone: true }).defaultNow().notNull(),
}, (table) => ({ auditOrgIndex: index('audit_log_org_created_idx').on(table.organizationId, table.createdAt) }));
