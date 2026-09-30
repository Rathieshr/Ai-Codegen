import * as SDK from 'azure-devops-extension-sdk';
import { getClient } from 'azure-devops-extension-api/Common/Client';
import { GraphTraversalDirection } from 'azure-devops-extension-api/Graph/Graph';
import { GraphRestClient } from 'azure-devops-extension-api/Graph/GraphClient';

export type HEIRole = 'admin' | 'contributor' | 'viewer';

export type PermissionState = {
  role: HEIRole;
  user_display_name: string;
  user_name: string;
  mapped_group: string;
  azure_groups: string[];
  status: 'resolved' | 'fallback';
  warning?: string;
  diagnostics: {
    matched_groups: string[];
    ignored_groups: string[];
    matched_roles: HEIRole[];
    selected_role: HEIRole;
    precedence_rule: string;
  };
};

type AzureDevOpsIdentity = {
  id?: string;
  descriptor?: string;
  subjectId?: string;
  displayName?: string;
  name?: string;
  uniqueName?: string;
  email?: string;
};

type GroupCandidate = { original: string; scope: string; name: string };

const ROLE_PRECEDENCE: HEIRole[] = ['admin', 'contributor', 'viewer'];
const ADMIN_GROUPS = new Set([
  'hei administrators',
  'hei admins',
  'project administrators',
  'project collection administrators',
  'collection administrators',
  'team foundation administrators',
]);
const CONTRIBUTOR_GROUPS = new Set(['hei contributors', 'contributors']);
const VIEWER_GROUPS = new Set(['hei readers', 'readers', 'stakeholders']);
const COLLECTION_ADMIN_GROUPS = new Set([
  'project collection administrators',
  'collection administrators',
  'team foundation administrators',
]);

export function defaultPermissionState(identity: Partial<AzureDevOpsIdentity> = {}): PermissionState {
  return permissionState(identity, 'viewer', 'Readers', [], 'fallback', 'Permission lookup is pending. Viewer access is applied until Azure DevOps groups are resolved.', {
    matched_groups: [],
    ignored_groups: [],
    matched_roles: [],
    selected_role: 'viewer',
    precedence_rule: 'fail_closed_viewer',
  });
}

export async function resolveAzureDevOpsPermission(projectName = ''): Promise<PermissionState> {
  const identity = currentIdentity();
  try {
    const graphClient = getClient(GraphRestClient);
    const descriptor = await resolveDescriptor(graphClient, identity);
    if (!descriptor) {
      return fallbackPermission(identity, 'Azure DevOps user descriptor could not be resolved. Viewer access is applied.');
    }

    let groupNames = await collectGroupNames(graphClient, descriptor);
    if (!groupNames.length) groupNames = await collectGroupsViaRestApi(descriptor);
    if (!groupNames.length) {
      return fallbackPermission(identity, 'Azure DevOps returned no visible group memberships. Viewer access is applied.');
    }

    const mapping = mapAzureDevOpsGroupsToRole(groupNames, projectName);
    const warning = mapping.diagnostics.matched_roles.length
      ? undefined
      : 'Azure DevOps groups were resolved, but none map to an HEI role for this project. Viewer access is applied.';
    return permissionState(identity, mapping.role, mapping.group, groupNames, 'resolved', warning, mapping.diagnostics);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return fallbackPermission(identity, `Could not resolve Azure DevOps group membership. Viewer access is applied. ${detail}`);
  }
}

export function mapAzureDevOpsGroupsToRole(
  groupNames: string[],
  projectName: string,
): { role: HEIRole; group: string; diagnostics: PermissionState['diagnostics'] } {
  const matched = new Map<HEIRole, string[]>();
  const ignored: string[] = [];

  unique(groupNames).forEach((original) => {
    const candidate = parseGroup(original);
    const role = roleForGroup(candidate, projectName);
    if (!role) {
      ignored.push(original);
      return;
    }
    matched.set(role, [...(matched.get(role) || []), original]);
  });

  const selectedRole = ROLE_PRECEDENCE.find((role) => matched.has(role)) || 'viewer';
  const selectedGroups = matched.get(selectedRole) || [];
  const selectedGroup = selectedGroups[0] || 'Readers';
  const matchedRoles = ROLE_PRECEDENCE.filter((role) => matched.has(role));
  const precedenceRule = selectedRole === 'admin'
    ? 'admin_takes_precedence'
    : selectedRole === 'contributor'
      ? 'contributor_takes_precedence_over_viewer'
      : matched.has('viewer')
        ? 'viewer_group_matched'
        : 'fail_closed_viewer';

  return {
    role: selectedRole,
    group: selectedGroup,
    diagnostics: {
      matched_groups: [...matched.values()].flat(),
      ignored_groups: ignored,
      matched_roles: matchedRoles,
      selected_role: selectedRole,
      precedence_rule: precedenceRule,
    },
  };
}

function roleForGroup(candidate: GroupCandidate, projectName: string): HEIRole | undefined {
  const isHeiGroup = candidate.name.startsWith('hei ');
  const isCollectionAdmin = COLLECTION_ADMIN_GROUPS.has(candidate.name);
  const scopedToCurrentProject = Boolean(projectName) && candidate.scope === normalize(projectName);
  const isUnscoped = !candidate.scope;
  if (!isHeiGroup && !isCollectionAdmin && !isUnscoped && !scopedToCurrentProject) return undefined;
  if (ADMIN_GROUPS.has(candidate.name)) return 'admin';
  if (CONTRIBUTOR_GROUPS.has(candidate.name)) return 'contributor';
  if (VIEWER_GROUPS.has(candidate.name)) return 'viewer';
  return undefined;
}

function parseGroup(value: string): GroupCandidate {
  const original = String(value || '').trim();
  const match = original.match(/^\[([^\]]+)\][\\/](.+)$/);
  return {
    original,
    scope: normalize(match?.[1] || ''),
    name: normalize(match?.[2] || original),
  };
}

function currentIdentity(): AzureDevOpsIdentity {
  const sdkUser = (SDK.getUser() || {}) as AzureDevOpsIdentity;
  const webUser = ((SDK.getWebContext() as unknown as { user?: AzureDevOpsIdentity }).user || {});
  return {
    ...webUser,
    ...sdkUser,
    id: sdkUser.id || webUser.id,
    descriptor: sdkUser.descriptor || webUser.descriptor,
    subjectId: sdkUser.subjectId || webUser.subjectId,
    displayName: sdkUser.displayName || sdkUser.name || webUser.displayName || webUser.name,
    name: sdkUser.name || sdkUser.displayName || webUser.name || webUser.displayName,
    uniqueName: sdkUser.uniqueName || sdkUser.email || webUser.uniqueName || webUser.email,
    email: sdkUser.email || sdkUser.uniqueName || webUser.email || webUser.uniqueName,
  };
}

async function resolveDescriptor(graphClient: GraphRestClient, identity: AzureDevOpsIdentity): Promise<string> {
  if (identity.descriptor) return identity.descriptor;
  for (const storageKey of unique([identity.id || '', identity.subjectId || ''])) {
    try {
      const descriptor = await graphClient.getDescriptor(storageKey);
      if (descriptor?.value) return descriptor.value;
    } catch {
      // Continue with the REST fallback below.
    }
    const descriptor = await descriptorViaRestApi(storageKey).catch(() => '');
    if (descriptor) return descriptor;
  }
  return '';
}

async function collectGroupNames(graphClient: GraphRestClient, userDescriptor: string): Promise<string[]> {
  const visited = new Set<string>([userDescriptor]);
  let frontier = [userDescriptor];
  const names: string[] = [];
  for (let depth = 0; depth < 4 && frontier.length; depth += 1) {
    const memberships = (await Promise.all(frontier.map(async (descriptor) => {
      try { return await graphClient.listMemberships(descriptor, GraphTraversalDirection.Up, 1); }
      catch { return []; }
    }))).flat();
    const next = unique(memberships.map((item) => item.containerDescriptor || '').filter(Boolean))
      .filter((descriptor) => !visited.has(descriptor));
    next.forEach((descriptor) => visited.add(descriptor));
    const subjects = await Promise.all(next.map(async (descriptor) => {
      try { return await graphClient.getSubject(descriptor); }
      catch { return undefined; }
    }));
    subjects.forEach((subject) => {
      const value = subject as unknown as { principalName?: string; displayName?: string } | undefined;
      const name = value?.principalName || value?.displayName;
      if (name) names.push(name);
    });
    frontier = next;
  }
  return unique(names);
}

async function descriptorViaRestApi(storageKey: string): Promise<string> {
  const response = await graphFetch(`descriptors/${encodeURIComponent(storageKey)}`);
  return response.ok ? String((await response.json()).value || '') : '';
}

async function collectGroupsViaRestApi(userDescriptor: string): Promise<string[]> {
  const response = await graphFetch(`memberships/${encodeURIComponent(userDescriptor)}?direction=Up&depth=1`);
  if (!response.ok) return [];
  const payload = await response.json();
  const descriptors = unique((payload.value || []).map((item: { containerDescriptor?: string }) => item.containerDescriptor || '').filter(Boolean));
  const subjects = await Promise.all(descriptors.map(async (descriptor) => {
    const subject = await graphFetch(`subjects/${encodeURIComponent(descriptor)}`);
    return subject.ok ? subject.json() : undefined;
  }));
  return unique(subjects.map((subject) => subject?.principalName || subject?.displayName || '').filter(Boolean));
}

async function graphFetch(path: string): Promise<Response> {
  const token = await SDK.getAccessToken();
  const collectionUri = collectionUrl();
  const separator = path.includes('?') ? '&' : '?';
  return fetch(`${collectionUri}/_apis/graph/${path}${separator}api-version=7.1-preview.1`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
  });
}

function collectionUrl(): string {
  const page = SDK.getPageContext() as unknown as { webContext?: { collection?: { uri?: string }; account?: { uri?: string } } };
  const web = SDK.getWebContext() as unknown as { collection?: { uri?: string }; account?: { uri?: string } };
  return String(page.webContext?.collection?.uri || page.webContext?.account?.uri || web.collection?.uri || web.account?.uri || window.location.origin).replace(/\/$/, '');
}

function fallbackPermission(identity: AzureDevOpsIdentity, warning: string): PermissionState {
  return permissionState(identity, 'viewer', 'Readers', [], 'fallback', warning, {
    matched_groups: [],
    ignored_groups: [],
    matched_roles: [],
    selected_role: 'viewer',
    precedence_rule: 'fail_closed_viewer',
  });
}

function permissionState(
  identity: Partial<AzureDevOpsIdentity>,
  role: HEIRole,
  group: string,
  groups: string[],
  status: PermissionState['status'],
  warning: string | undefined,
  diagnostics: PermissionState['diagnostics'],
): PermissionState {
  return {
    role,
    user_display_name: identity.displayName || identity.name || '',
    user_name: identity.uniqueName || identity.email || identity.name || '',
    mapped_group: group,
    azure_groups: unique(groups),
    status,
    warning,
    diagnostics,
  };
}

function normalize(value: string): string {
  return String(value || '').toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
}

function unique(values: string[]): string[] {
  return [...new Set(values.map((value) => String(value || '').trim()).filter(Boolean))];
}
