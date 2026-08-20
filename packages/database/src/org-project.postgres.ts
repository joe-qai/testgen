import { eq, and } from 'drizzle-orm';
import * as schema from './schema.js';
import type { Database as TestgenDatabase } from './client.js';
import type { OrganizationStore, OrganizationRecord, ProjectStore, ProjectRecord, ProjectMemberRecord } from './org-project.stores.js';

type Db = TestgenDatabase;

export class PostgresOrganizationStore implements OrganizationStore {
  constructor(private readonly db: Db) {}

  private toRecord(row: typeof schema.organizations.$inferSelect): OrganizationRecord {
    return { id: row.id, name: row.name, slug: row.slug, status: row.status, logoUrl: row.logoUrl, createdAt: row.createdAt.toISOString() };
  }

  async findById(id: string): Promise<OrganizationRecord | null> {
    const [row] = await this.db.select().from(schema.organizations).where(eq(schema.organizations.id, id)).limit(1);
    return row ? this.toRecord(row) : null;
  }

  async findBySlug(slug: string): Promise<OrganizationRecord | null> {
    const [row] = await this.db.select().from(schema.organizations).where(eq(schema.organizations.slug, slug)).limit(1);
    return row ? this.toRecord(row) : null;
  }

  async listByUser(userId: string): Promise<OrganizationRecord[]> {
    const rows = await this.db
      .select({ organization: schema.organizations })
      .from(schema.organizationMembers)
      .innerJoin(schema.organizations, eq(schema.organizations.id, schema.organizationMembers.organizationId))
      .where(eq(schema.organizationMembers.userId, userId));
    return rows.map((item) => this.toRecord(item.organization));
  }

  async create(input: { name: string; slug: string; createdBy: string }): Promise<OrganizationRecord> {
    const [row] = await this.db.insert(schema.organizations).values({ name: input.name, slug: input.slug, createdBy: input.createdBy }).returning();
    return this.toRecord(row);
  }

  async addMember(organizationId: string, userId: string): Promise<void> {
    await this.db.insert(schema.organizationMembers).values({ organizationId, userId }).onConflictDoNothing();
  }

  async isMember(organizationId: string, userId: string): Promise<boolean> {
    const [row] = await this.db
      .select({ id: schema.organizationMembers.id })
      .from(schema.organizationMembers)
      .where(and(eq(schema.organizationMembers.organizationId, organizationId), eq(schema.organizationMembers.userId, userId)))
      .limit(1);
    return Boolean(row);
  }
}

export class PostgresProjectStore implements ProjectStore {
  constructor(private readonly db: Db) {}

  private toRecord(row: typeof schema.projects.$inferSelect): ProjectRecord {
    return { id: row.id, organizationId: row.organizationId, key: row.key, name: row.name, description: row.description, status: row.status, ownerId: row.ownerId, createdAt: row.createdAt.toISOString() };
  }

  private toMember(row: typeof schema.projectMembers.$inferSelect): ProjectMemberRecord {
    return { id: row.id, organizationId: row.organizationId, projectId: row.projectId, userId: row.userId, status: row.status, joinedAt: row.joinedAt.toISOString() };
  }

  async findById(id: string): Promise<ProjectRecord | null> {
    const [row] = await this.db.select().from(schema.projects).where(eq(schema.projects.id, id)).limit(1);
    return row ? this.toRecord(row) : null;
  }

  async listByOrganization(organizationId: string): Promise<ProjectRecord[]> {
    const rows = await this.db.select().from(schema.projects).where(eq(schema.projects.organizationId, organizationId));
    return rows.map(this.toRecord);
  }

  async create(input: { organizationId: string; key: string; name: string; description?: string | null; ownerId: string; createdBy: string; updatedBy: string }): Promise<ProjectRecord> {
    const [row] = await this.db.insert(schema.projects).values({ organizationId: input.organizationId, key: input.key, name: input.name, description: input.description ?? null, ownerId: input.ownerId, createdBy: input.createdBy, updatedBy: input.updatedBy }).returning();
    return this.toRecord(row);
  }

  async listMembers(projectId: string): Promise<ProjectMemberRecord[]> {
    const rows = await this.db.select().from(schema.projectMembers).where(eq(schema.projectMembers.projectId, projectId));
    return rows.map(this.toMember);
  }

  async addMember(input: { organizationId: string; projectId: string; userId: string; invitedBy: string }): Promise<ProjectMemberRecord> {
    const [row] = await this.db.insert(schema.projectMembers).values({ organizationId: input.organizationId, projectId: input.projectId, userId: input.userId, invitedBy: input.invitedBy }).onConflictDoNothing().returning();
    if (!row) {
      const [existing] = await this.db.select().from(schema.projectMembers).where(and(eq(schema.projectMembers.projectId, input.projectId), eq(schema.projectMembers.userId, input.userId))).limit(1);
      if (!existing) throw new Error('Failed to add project member');
      return this.toMember(existing);
    }
    return this.toMember(row);
  }

  async isMember(projectId: string, userId: string): Promise<boolean> {
    const [row] = await this.db
      .select({ id: schema.projectMembers.id })
      .from(schema.projectMembers)
      .where(and(eq(schema.projectMembers.projectId, projectId), eq(schema.projectMembers.userId, userId)))
      .limit(1);
    return Boolean(row);
  }
}