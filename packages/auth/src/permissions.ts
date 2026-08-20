export type PermissionCode = `${string}:${string}`;

export type AuthorizationContext = {
  userId: string;
  organizationId?: string;
  projectId?: string;
  isPlatformAdmin: boolean;
  permissions: ReadonlySet<PermissionCode>;
};

export function hasPermission(context: AuthorizationContext, permission: PermissionCode): boolean {
  return context.isPlatformAdmin || context.permissions.has(permission);
}
