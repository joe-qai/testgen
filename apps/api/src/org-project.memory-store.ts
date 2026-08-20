import type { OrganizationStore, OrganizationRecord, ProjectStore, ProjectRecord, ProjectMemberRecord } from '@testgen/database';

export function createMemoryOrganizationStore(): OrganizationStore {
  const organizations: OrganizationRecord[] = [];
  const members: Array<{ organizationId: string; userId: string }> = [];

  return {
    async findById(id) { return organizations.find((item) => item.id === id) ?? null; },
    async findBySlug(slug) { return organizations.find((item) => item.slug === slug) ?? null; },
    async listByUser(userId) { return organizations.filter((item) => members.some((m) => m.organizationId === item.id && m.userId === userId)); },
    async create(input) {
      const record: OrganizationRecord = { id: crypto.randomUUID(), name: input.name, slug: input.slug, status: 'ACTIVE', logoUrl: null, createdAt: new Date().toISOString() };
      organizations.push(record);
      return record;
    },
    async addMember(organizationId, userId) { members.push({ organizationId, userId }); },
    async isMember(organizationId, userId) { return members.some((m) => m.organizationId === organizationId && m.userId === userId); },
  };
}

export function createMemoryProjectStore(): ProjectStore {
  const projects: ProjectRecord[] = [];
  const members: ProjectMemberRecord[] = [];

  return {
    async findById(id) { return projects.find((item) => item.id === id) ?? null; },
    async listByOrganization(organizationId) { return projects.filter((item) => item.organizationId === organizationId); },
    async create(input) {
      const record: ProjectRecord = { id: crypto.randomUUID(), organizationId: input.organizationId, key: input.key, name: input.name, description: input.description ?? null, status: 'ACTIVE', ownerId: input.ownerId, createdAt: new Date().toISOString() };
      projects.push(record);
      return record;
    },
    async listMembers(projectId) { return members.filter((item) => item.projectId === projectId); },
    async addMember(input) {
      const record: ProjectMemberRecord = { id: crypto.randomUUID(), organizationId: input.organizationId, projectId: input.projectId, userId: input.userId, status: 'ACTIVE', joinedAt: new Date().toISOString() };
      members.push(record);
      return record;
    },
    async isMember(projectId, userId) { return members.some((item) => item.projectId === projectId && item.userId === userId); },
  };
}