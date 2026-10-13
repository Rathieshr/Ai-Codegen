import * as SDK from 'azure-devops-extension-sdk';
import { getClient } from 'azure-devops-extension-api/Common/Client';
import { GraphTraversalDirection } from 'azure-devops-extension-api/Graph/Graph';
import { GraphRestClient } from 'azure-devops-extension-api/Graph/GraphClient';

import type { HEIRole } from './rolePolicy';
export type { HEIRole } from './rolePolicy';

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

const ROLE_PRECEDENCE: HEIRole[] = ['admin', 'manager', 'developer', 'tester', 'collaborator', 'reader', 'contributor', 'viewer'];
const NAMED_GROUPS: Record<string, HEIRole> = {
  manager: 'manager', tester: 'tester', developer: 'developer', collaborator: 'collaborator', reader: 'reader',
  'hei manager': 'manager', 'hei managers': 'manager',
  'hei developer': 'developer', 'hei developers': 'developer',
  'hei tester': 'tester', 'hei testers': 'tester',
  'hei collaborator': 'collaborator', 'hei collaborators': 'collaborator',
  'hei reader': 'reader', 'hei readers': 'reader',
};
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

    const groupNames = await collectGroupNames(graphClient, descriptor);
    if (!groupNames.length) {
      return fallbackPermission(identity, 'Azure DevOps returned no visible group memberships. Viewer access is applied.');
    }

    const organizationName = String((SDK.getHost() as unknown as { name?: string })?.name || '');
    const mapping = mapAzureDevOpsGroupsToRole(groupNames, projectName, organizationName);
    const warning = mapping.diagnostics.matched_roles.length
      ? undefined
      : 'Azure DevOps groups were resolved, but none map to an HEI role for this project. Viewer access is applied.';
    return permissionState(identity, mapping.role, mapping.group, groupNames, warning ? 'fallback' : 'resolved', warning, mapping.diagnostics);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return fallbackPermission(identity, `Could not resolve Azure DevOps group membership. Viewer access is applied. ${detail}`);
  }
}

export function mapAzureDevOpsGroupsToRole(
  groupNames: string[],
  projectName: string,
  organizationName = '',
): { role: HEIRole; group: string; diagnostics: PermissionState['diagnostics'] } {
  const matched = new Map<HEIRole, string[]>();
  const explicitHeiMatches = new Map<HEIRole, string[]>();
  const ignored: string[] = [];

  unique(groupNames).forEach((original) => {
    const candidate = parseGroup(original);
    const role = roleForGroup(candidate, projectName, organizationName);
    if (!role) {
      ignored.push(original);
      return;
    }
    matched.set(role, [...(matched.get(role) || []), original]);
    if (candidate.name.startsWith('hei ') || NAMED_GROUPS[candidate.name]) {
      explicitHeiMatches.set(role, [...(explicitHeiMatches.get(role) || []), original]);
    }
  });

  const explicitOverrideApplied = !matched.has('admin') && explicitHeiMatches.size > 0;
  const selectionPool = explicitOverrideApplied ? explicitHeiMatches : matched;
  const selectedRole = ROLE_PRECEDENCE.find((role) => selectionPool.has(role)) || 'viewer';
  const selectedGroups = selectionPool.get(selectedRole) || [];
  const selectedGroup = selectedGroups[0] || 'Readers';
  const matchedRoles = ROLE_PRECEDENCE.filter((role) => matched.has(role));
  const precedenceRule = explicitOverrideApplied
    ? `explicit_hei_${selectedRole}_override`
    : selectedRole === 'admin'
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

function roleForGroup(candidate: GroupCandidate, projectName: string, organizationName: string): HEIRole | undefined {
  const isHeiGroup = candidate.name.startsWith('hei ');
  const isCollectionAdmin = COLLECTION_ADMIN_GROUPS.has(candidate.name);
  const scopedToCurrentProject = Boolean(projectName) && candidate.scope === normalize(projectName);
  const scopedToCurrentOrganization = Boolean(organizationName) && candidate.scope === normalize(organizationName);
  const isUnscoped = !candidate.scope;
  if (projectName && isUnscoped && !isHeiGroup && !isCollectionAdmin) return undefined;
  if (!isCollectionAdmin && !isUnscoped && !scopedToCurrentProject && !(isHeiGroup && scopedToCurrentOrganization)) return undefined;
  if (ADMIN_GROUPS.has(candidate.name)) return 'admin';
  if (NAMED_GROUPS[candidate.name]) return NAMED_GROUPS[candidate.name];
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
  if (identity.descriptor && /^(aad|msa|svc|imp|vss)\./.test(identity.descriptor)) return identity.descriptor;
  for (const storageKey of unique([identity.id || '', identity.subjectId || ''])) {
    try {
      const descriptor = await bounded(graphClient.getDescriptor(storageKey));
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
  for (let depth = 0; depth < 16 && frontier.length; depth += 1) {
    const memberships = (await Promise.all(frontier.map(async (descriptor) => {
      try { return await bounded(graphClient.listMemberships(descriptor, GraphTraversalDirection.Up, 1)); }
      catch {
        const response = await graphFetch(`memberships/${encodeURIComponent(descriptor)}?direction=Up&depth=1`);
        return (await response.json()).value || [];
      }
    }))).flat();
    const next = unique(memberships.map((item) => item.containerDescriptor || '').filter(Boolean))
      .filter((descriptor) => !visited.has(descriptor));
    next.forEach((descriptor) => visited.add(descriptor));
    const subjects = await Promise.all(next.map(async (descriptor) => {
      try { return await bounded(graphClient.getGroup(descriptor)); }
      catch { return (await graphFetch(`groups/${encodeURIComponent(descriptor)}`)).json(); }
    }));
    subjects.forEach((subject) => {
      const value = subject as unknown as { principalName?: string; displayName?: string } | undefined;
      const name = value?.principalName || value?.displayName;
      if (name) names.push(name);
    });
    frontier = next;
  }
  if (frontier.length) throw new Error('Group nesting exceeds the supported depth. Permission resolution is incomplete.');
  return unique(names);
}

async function descriptorViaRestApi(storageKey: string): Promise<string> {
  const response = await graphFetch(`descriptors/${encodeURIComponent(storageKey)}`);
  return response.ok ? String((await response.json()).value || '') : '';
}

async function graphFetch(path: string): Promise<Response> {
  const token = await bounded(SDK.getAccessToken());
  const collectionUri = graphServiceUrl(collectionUrl());
  const separator = path.includes('?') ? '&' : '?';
  const response = await fetch(`${collectionUri}/_apis/graph/${path}${separator}api-version=7.1-preview.1`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) throw new Error(`Azure DevOps Graph returned HTTP ${response.status}. Verify the installed extension's vso.graph scope in Organization settings > Extensions.`);
  return response;
}

export function graphServiceUrl(collectionUri: string): string {
  const url = new URL(collectionUri);
  if (url.hostname === 'dev.azure.com') {
    const organization = url.pathname.split('/').filter(Boolean)[0];
    if (!organization) throw new Error('Azure DevOps organization is missing.');
    return `https://vssps.dev.azure.com/${organization}`;
  }
  if (url.hostname.endsWith('.visualstudio.com')) return `https://${url.hostname.replace(/\.visualstudio\.com$/, '.vssps.visualstudio.com')}`;
  throw new Error('HEI group lookup requires an Azure DevOps Services organization URL.');
}

function bounded<T>(request: Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Azure DevOps Graph request timed out.')), 5000);
    request.then(resolve, reject).finally(() => clearTimeout(timer));
  });
}

function collectionUrl(): string {
  const page = SDK.getPageContext() as unknown as { webContext?: { collection?: { uri?: string }; account?: { uri?: string } } };
  const web = SDK.getWebContext() as unknown as { collection?: { uri?: string }; account?: { uri?: string } };
  const contextUrl = page.webContext?.collection?.uri || page.webContext?.account?.uri || web.collection?.uri || web.account?.uri;
  if (contextUrl) return String(contextUrl).replace(/\/$/, '');
  const host = SDK.getHost() as unknown as { name?: string; isHosted?: boolean };
  if (host?.isHosted !== false && host?.name) return `https://dev.azure.com/${encodeURIComponent(host.name)}`;
  const referrer = document.referrer;
  if (referrer) {
    const referrerUrl = new URL(referrer);
    if (referrerUrl.hostname === 'dev.azure.com' && referrerUrl.pathname.split('/').filter(Boolean)[0]) {
      return `https://dev.azure.com/${referrerUrl.pathname.split('/').filter(Boolean)[0]}`;
    }
    if (referrerUrl.hostname.endsWith('.visualstudio.com')) return referrerUrl.origin;
  }
  return window.location.origin.replace(/\/$/, '');
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
