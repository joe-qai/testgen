import { sql } from 'drizzle-orm';

export const rlsPolicySql = sql`
  create schema if not exists app;

  create or replace function app_user_id() returns uuid language sql stable as $$
    select nullif(current_setting('app.user_id', true), '')::uuid
  $$;
  create or replace function app_organization_id() returns uuid language sql stable as $$
    select nullif(current_setting('app.organization_id', true), '')::uuid
  $$;
  create or replace function app_project_id() returns uuid language sql stable as $$
    select nullif(current_setting('app.project_id', true), '')::uuid
  $$;
  create or replace function app_is_platform_admin() returns boolean language sql stable as $$
    select coalesce(current_setting('app.is_platform_admin', true), 'false') = 'true'
  $$;

  alter table organizations enable row level security;
  alter table organization_members enable row level security;
  alter table projects enable row level security;
  alter table project_members enable row level security;
  alter table workflow_runs enable row level security;
  alter table workflow_node_runs enable row level security;
  alter table workflow_events enable row level security;
  alter table audit_logs enable row level security;

  drop policy if exists organizations_tenant_policy on organizations;
  create policy organizations_tenant_policy on organizations
    using (app_is_platform_admin() or id = app_organization_id());

  drop policy if exists organization_members_tenant_policy on organization_members;
  create policy organization_members_tenant_policy on organization_members
    using (app_is_platform_admin() or organization_id = app_organization_id());

  drop policy if exists projects_tenant_policy on projects;
  create policy projects_tenant_policy on projects
    using (app_is_platform_admin() or organization_id = app_organization_id());

  drop policy if exists project_members_tenant_policy on project_members;
  create policy project_members_tenant_policy on project_members
    using (app_is_platform_admin() or organization_id = app_organization_id());

  drop policy if exists workflow_runs_tenant_policy on workflow_runs;
  create policy workflow_runs_tenant_policy on workflow_runs
    using (app_is_platform_admin() or (organization_id = app_organization_id() and (app_project_id() is null or project_id = app_project_id())));

  drop policy if exists workflow_node_runs_tenant_policy on workflow_node_runs;
  create policy workflow_node_runs_tenant_policy on workflow_node_runs
    using (app_is_platform_admin() or (organization_id = app_organization_id() and (app_project_id() is null or project_id = app_project_id())));

  drop policy if exists workflow_events_tenant_policy on workflow_events;
  create policy workflow_events_tenant_policy on workflow_events
    using (app_is_platform_admin() or (organization_id = app_organization_id() and (app_project_id() is null or project_id = app_project_id())));

  drop policy if exists audit_logs_tenant_policy on audit_logs;
  create policy audit_logs_tenant_policy on audit_logs
    using (app_is_platform_admin() or organization_id = app_organization_id());
`;
