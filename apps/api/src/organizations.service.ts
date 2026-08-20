import type { OrganizationStore, OrganizationRecord } from '@testgen/database';

export class OrganizationsService {
  constructor(private readonly store: OrganizationStore) {}

  async listForUser(userId: string): Promise<OrganizationRecord[]> {
    return this.store.listByUser(userId);
  }

  async create(input: { name: string; createdBy: string }): Promise<OrganizationRecord> {
    const slug = Array.from(input.name.toLowerCase()).map((char) => (/[a-z0-9一-龥]/.test(char) ? char : '-')).join('').replace(/-+/g, '-').replace(/(^-|-$)/g, '') || `org-${Math.random().toString(36).slice(2, 8)}`;
    const existing = await this.store.findBySlug(slug);
    if (existing) throw new Error(`Organization slug already exists: ${slug}`);
    const organization = await this.store.create({ name: input.name, slug, createdBy: input.createdBy });
    await this.store.addMember(organization.id, input.createdBy);
    return organization;
  }

  async isMember(organizationId: string, userId: string): Promise<boolean> {
    return this.store.isMember(organizationId, userId);
  }
}