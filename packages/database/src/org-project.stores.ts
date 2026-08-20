export type OrganizationRecord = {
  id: string;
  name: string;
  slug: string;
  status: string;
  logoUrl: string | null;
  createdAt: string;
};

export type ProjectRecord = {
  id: string;
  organizationId: string;
  key: string;
  name: string;
  description: string | null;
  status: string;
  ownerId: string;
  createdAt: string;
};

export type ProjectMemberRecord = {
  id: string;
  organizationId: string;
  projectId: string;
  userId: string;
  status: string;
  joinedAt: string;
};

export interface OrganizationStore {
  findById(id: string): Promise<OrganizationRecord | null>;
  findBySlug(slug: string): Promise<OrganizationRecord | null>;
  listByUser(userId: string): Promise<OrganizationRecord[]>;
  create(input: { name: string; slug: string; createdBy: string }): Promise<OrganizationRecord>;
  addMember(organizationId: string, userId: string): Promise<void>;
  isMember(organizationId: string, userId: string): Promise<boolean>;
}

export interface ProjectStore {
  findById(id: string): Promise<ProjectRecord | null>;
  listByOrganization(organizationId: string): Promise<ProjectRecord[]>;
  create(input: { organizationId: string; key: string; name: string; description?: string | null; ownerId: string; createdBy: string; updatedBy: string }): Promise<ProjectRecord>;
  listMembers(projectId: string): Promise<ProjectMemberRecord[]>;
  addMember(input: { organizationId: string; projectId: string; userId: string; invitedBy: string }): Promise<ProjectMemberRecord>;
  isMember(projectId: string, userId: string): Promise<boolean>;
}