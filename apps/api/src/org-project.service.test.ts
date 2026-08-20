import { describe, expect, it } from 'vitest';
import type { OrganizationStore, OrganizationRecord, ProjectStore, ProjectRecord, ProjectMemberRecord } from '@testgen/database';
import { OrganizationsService } from './organizations.service.js';
import { ProjectsService } from './projects.service.js';

class InMemoryOrganizationStore implements OrganizationStore {
  organizations: OrganizationRecord[] = [];
  members: Array<{ organizationId: string; userId: string }> = [];
  async findById(id: string) { return this.organizations.find((item) => item.id === id) ?? null; }
  async findBySlug(slug: string) { return this.organizations.find((item) => item.slug === slug) ?? null; }
  async listByUser(userId: string) { return this.organizations.filter((item) => this.members.some((m) => m.organizationId === item.id && m.userId === userId)); }
  async create(input: { name: string; slug: string; createdBy: string }) {
    const record: OrganizationRecord = { id: `org-${this.organizations.length + 1}`, name: input.name, slug: input.slug, status: 'ACTIVE', logoUrl: null, createdAt: new Date().toISOString() };
    this.organizations.push(record);
    return record;
  }
  async addMember(organizationId: string, userId: string) { this.members.push({ organizationId, userId }); }
  async isMember(organizationId: string, userId: string) { return this.members.some((m) => m.organizationId === organizationId && m.userId === userId); }
}

class InMemoryProjectStore implements ProjectStore {
  projects: ProjectRecord[] = [];
  members: ProjectMemberRecord[] = [];
  async findById(id: string) { return this.projects.find((item) => item.id === id) ?? null; }
  async listByOrganization(organizationId: string) { return this.projects.filter((item) => item.organizationId === organizationId); }
  async create(input: { organizationId: string; key: string; name: string; description?: string | null; ownerId: string; createdBy: string; updatedBy: string }) {
    const record: ProjectRecord = { id: `project-${this.projects.length + 1}`, organizationId: input.organizationId, key: input.key, name: input.name, description: input.description ?? null, status: 'ACTIVE', ownerId: input.ownerId, createdAt: new Date().toISOString() };
    this.projects.push(record);
    return record;
  }
  async listMembers(projectId: string) { return this.members.filter((item) => item.projectId === projectId); }
  async addMember(input: { organizationId: string; projectId: string; userId: string; invitedBy: string }) {
    const record: ProjectMemberRecord = { id: `pm-${this.members.length + 1}`, organizationId: input.organizationId, projectId: input.projectId, userId: input.userId, status: 'ACTIVE', joinedAt: new Date().toISOString() };
    this.members.push(record);
    return record;
  }
  async isMember(projectId: string, userId: string) { return this.members.some((item) => item.projectId === projectId && item.userId === userId); }
}

describe('organizations service', () => {
  it('creates an organization with generated slug and adds creator as member', async () => {
    const service = new OrganizationsService(new InMemoryOrganizationStore());
    const org = await service.create({ name: '测试组织', createdBy: 'user-1' });
    expect(org.slug).toBe('测试组织');
    expect(await service.isMember(org.id, 'user-1')).toBe(true);
    expect(await service.isMember(org.id, 'user-2')).toBe(false);
  });

  it('rejects duplicate organization slug', async () => {
    const service = new OrganizationsService(new InMemoryOrganizationStore());
    await service.create({ name: '测试组织', createdBy: 'user-1' });
    await expect(service.create({ name: '测试组织', createdBy: 'user-1' })).rejects.toThrow('slug already exists');
  });

  it('lists organizations a user belongs to', async () => {
    const service = new OrganizationsService(new InMemoryOrganizationStore());
    const orgA = await service.create({ name: '组织A', createdBy: 'user-1' });
    await service.create({ name: '组织B', createdBy: 'user-1' });
    await service.create({ name: '组织C', createdBy: 'user-2' });
    const mine = await service.listForUser('user-1');
    expect(mine.map((item) => item.id)).toContain(orgA.id);
    expect(mine).toHaveLength(2);
  });
});

describe('projects service', () => {
  it('creates and lists projects by organization', async () => {
    const store = new InMemoryProjectStore();
    const service = new ProjectsService(store);
    const project = await service.create({ organizationId: 'org-1', key: 'DEMO', name: '演示项目', ownerId: 'user-1', actorId: 'user-1' });
    expect(project.key).toBe('DEMO');
    const list = await service.list('org-1');
    expect(list).toHaveLength(1);
    const detail = await service.detail(project.id);
    expect(detail?.name).toBe('演示项目');
  });

  it('adds and lists project members, and checks membership', async () => {
    const store = new InMemoryProjectStore();
    const service = new ProjectsService(store);
    const project = await service.create({ organizationId: 'org-1', key: 'DEMO', name: '演示', ownerId: 'user-1', actorId: 'user-1' });
    await service.addMember({ organizationId: 'org-1', projectId: project.id, userId: 'user-2', actorId: 'user-1' });
    expect(await service.isMember(project.id, 'user-2')).toBe(true);
    const members = await service.listMembers(project.id);
    expect(members).toHaveLength(1);
    expect(members[0].userId).toBe('user-2');
  });
});