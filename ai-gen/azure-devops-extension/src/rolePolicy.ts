export type HEIRole = 'admin' | 'manager' | 'developer' | 'tester' | 'collaborator' | 'reader' | 'contributor' | 'viewer';
export type HEIAction = 'configure' | 'plan' | 'execute' | 'test' | 'approve';

const ACTIONS: Record<HEIRole, readonly HEIAction[]> = {
  admin: ['configure', 'plan', 'execute', 'test', 'approve'],
  manager: ['configure', 'plan', 'execute', 'test', 'approve'],
  developer: ['plan', 'execute', 'test'],
  tester: ['test'],
  collaborator: ['plan'],
  reader: [],
  contributor: ['plan', 'execute', 'test', 'approve'],
  viewer: [],
};

export function canPerform(role: string, action: HEIAction): boolean {
  return Object.prototype.hasOwnProperty.call(ACTIONS, role) && ACTIONS[role as HEIRole].includes(action);
}

export function permissionRoleLabel(role: string): string {
  const names: Record<HEIRole, string> = { admin: 'Administrator', manager: 'Manager', developer: 'Developer', tester: 'Tester', collaborator: 'Collaborator', reader: 'Reader', contributor: 'Contributor', viewer: 'Reader' };
  return `HEI ${names[role as HEIRole] || 'Reader'}`;
}

export function canOpenWorkspace(role: string, workspace: string): boolean {
  if (['settings', 'administration', 'admin'].includes(workspace)) return canPerform(role, 'configure');
  if (['new-requirement', 'planning'].includes(workspace)) return canPerform(role, 'plan');
  if (['execution', 'agents', 'skills'].includes(workspace)) return canPerform(role, 'execute');
  if (workspace === 'qa') return canPerform(role, 'test');
  if (['approvals', 'governance'].includes(workspace)) return canPerform(role, 'approve');
  return ['overview', 'repository', 'azure-devops', 'activity', 'health', 'diagnostics', 'memory', 'portfolio'].includes(workspace);
}
