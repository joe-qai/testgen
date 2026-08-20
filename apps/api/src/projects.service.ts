import type { ProjectStore, ProjectRecord, ProjectMemberRecord } from '@testgen/database';

export class ProjectsService {
  constructor(private readonly store: ProjectStore) {}

  async list(organizationId: string): Promise<ProjectRecord[]> {
    return this.store.listByOrganization(organizationId);
  }

  async detail(id: string): Promise<ProjectRecord | null> {
    return this.store.findById(id);
  }

  async create(input: { organizationId: string; key: string; name: string; description?: string | null; ownerId: string; actorId: string }): Promise<ProjectRecord> {
    return this.store.create({ ...input, createdBy: input.actorId, updatedBy: input.actorId });
  }

  async listMembers(projectId: string): Promise<ProjectMemberRecord[]> {
    return this.store.listMembers(projectId);
  }

  async addMember(input: { organizationId: string; projectId: string; userId: string; actorId: string }): Promise<ProjectMemberRecord> {
    return this.store.addMember({ ...input, invitedBy: input.actorId });
  }

  async isMember(projectId: string, userId: string): Promise<boolean> {
    return this.store.isMember(projectId, userId);
  }
}