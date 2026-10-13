const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function load(name, mocks = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../src', name + '.ts'), 'utf8');
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const exports = {};
  vm.runInNewContext(output, {
    exports, require: id => mocks[id] || {}, URL, AbortSignal, setTimeout, clearTimeout,
    fetch: mocks.fetch,
    window: mocks.window || { location: { origin: 'https://extension.invalid' } },
    document: mocks.document || { referrer: '' },
  });
  return exports;
}

const permissions = load('permissions');
const policy = load('rolePolicy');
test('project administrator wins over explicit Reader; other-project admin does not', () => {
  assert.equal(permissions.mapAzureDevOpsGroupsToRole(['[Project]\\Project Administrators', '[Project]\\HEI Readers'], 'Project').role, 'admin');
  assert.equal(permissions.mapAzureDevOpsGroupsToRole(['[Other]\\Project Administrators', '[Project]\\HEI Readers'], 'Project').role, 'reader');
  assert.equal(permissions.mapAzureDevOpsGroupsToRole(['[Other]\\HEI Managers'], 'Project').role, 'viewer');
});
test('organization-scoped HEI Administrators overrides project Contributors', () => {
  const groups = [
    '[LineDefender]\\Contributors',
    '[Ai Gen]\\Contributors',
    '[ExampleOrg]\\HEI Administrators',
  ];
  const mapping = permissions.mapAzureDevOpsGroupsToRole(groups, 'LineDefender', 'ExampleOrg');
  assert.equal(mapping.role, 'admin');
  assert.equal(mapping.group, '[ExampleOrg]\\HEI Administrators');
  assert.equal(mapping.diagnostics.precedence_rule, 'admin_takes_precedence');
  assert.equal(permissions.mapAzureDevOpsGroupsToRole(groups, 'LineDefender', 'another-org').role, 'contributor');
});
test('all five named roles override built-in Contributors', () => {
  for (const role of ['Manager', 'Tester', 'Developer', 'Collaborator', 'Reader']) {
    assert.equal(permissions.mapAzureDevOpsGroupsToRole(['[Project]\\Contributors', `[Project]\\HEI ${role}s`], 'Project').role, role.toLowerCase());
    assert.equal(permissions.mapAzureDevOpsGroupsToRole(['[Project]\\Contributors', `[Project]\\${role}`], 'Project').role, role.toLowerCase());
  }
});

test('unknown groups remain unverified rather than a confirmed Reader assignment', async () => {
  const client = {
    getDescriptor: async () => ({ value: 'aad.user' }),
    listMemberships: async descriptor => descriptor === 'aad.user' ? [{ containerDescriptor: 'group' }] : [],
    getGroup: async () => ({ principalName: '[Project]\\Unmapped Team' }),
  };
  const result = await fixture(client).resolveAzureDevOpsPermission('Project');
  assert.equal(result.status, 'fallback');
  assert.equal(result.role, 'viewer');
  assert.match(result.warning, /none map/);
});

test('cyclic nested memberships terminate', async () => {
  const client = {
    getDescriptor: async () => ({ value: 'aad.user' }),
    listMemberships: async descriptor => [{ containerDescriptor: descriptor === 'aad.user' ? 'group' : 'aad.user' }],
    getGroup: async () => ({ principalName: '[Project]\\HEI Readers' }),
  };
  assert.equal((await fixture(client).resolveAzureDevOpsPermission('Project')).role, 'reader');
});
test('role action boundaries fail closed', () => {
  assert.equal(policy.canPerform('manager', 'configure'), true);
  assert.equal(policy.canPerform('developer', 'execute'), true);
  assert.equal(policy.canPerform('developer', 'approve'), false);
  assert.equal(policy.canPerform('tester', 'test'), true);
  assert.equal(policy.canPerform('tester', 'plan'), false);
  assert.equal(policy.canPerform('collaborator', 'plan'), true);
  assert.equal(policy.canPerform('collaborator', 'execute'), false);
  for (const role of ['reader', 'viewer', 'unknown']) {
    for (const action of ['configure', 'plan', 'execute', 'test', 'approve']) assert.equal(policy.canPerform(role, action), false);
    assert.equal(policy.canOpenWorkspace(role, 'settings'), false);
  }
});
test('Graph endpoint uses organization identity service', () => {
  assert.equal(permissions.graphServiceUrl('https://dev.azure.com/example/'), 'https://vssps.dev.azure.com/example');
  assert.equal(permissions.graphServiceUrl('https://example.visualstudio.com/'), 'https://example.vssps.visualstudio.com');
  assert.throws(() => permissions.graphServiceUrl('https://extension.invalid/'));
});

function fixture(client, fetch, sdkOverrides = {}) {
  return load('permissions', {
    'azure-devops-extension-sdk': {
      getUser: () => ({ id: 'user-id', descriptor: 'Microsoft.Identity;legacy' }),
      getWebContext: () => ({ collection: { uri: 'https://dev.azure.com/example/' } }),
      getPageContext: () => ({}), getAccessToken: async () => 'test-token',
      getHost: () => ({ name: 'example', isHosted: true }),
      ...sdkOverrides,
    },
    'azure-devops-extension-api/Common/Client': { getClient: () => client },
    'azure-devops-extension-api/Graph/Graph': { GraphTraversalDirection: { Up: 1 } }, fetch,
  });
}

test('Hub resolves Graph through SDK host when collection URI is absent', async () => {
  const urls = [];
  const client = {
    getDescriptor: async () => ({ value: 'aad.user' }),
    listMemberships: async () => { throw Error('sdk'); },
    getGroup: async () => { throw Error('sdk'); },
  };
  const api = fixture(client, async url => {
    urls.push(url);
    return { ok: true, json: async () => url.includes('/groups/') ? { principalName: '[Project]\\HEI Managers' } : { value: url.includes('aad.user') ? [{ containerDescriptor: 'group' }] : [] } };
  }, {
    getWebContext: () => ({ project: { name: 'Project' } }),
    getPageContext: () => ({ webContext: { project: { name: 'Project' } } }),
    getHost: () => ({ name: 'rat-hiesh 91', isHosted: true }),
  });
  assert.equal((await api.resolveAzureDevOpsPermission('Project')).role, 'manager');
  assert.ok(urls.every(url => url.startsWith('https://vssps.dev.azure.com/rat-hiesh%2091/_apis/graph/')));
});
test('resolves legacy user descriptor and nested memberships through group endpoint', async () => {
  const client = {
    getDescriptor: async key => { assert.equal(key, 'user-id'); return { value: 'aad.user' }; },
    listMemberships: async descriptor => descriptor === 'aad.user' ? [{ containerDescriptor: 'team' }] : descriptor === 'team' ? [{ containerDescriptor: 'admin' }] : [],
    getGroup: async descriptor => ({ principalName: descriptor === 'team' ? '[Project]\\Team' : '[Project]\\Project Administrators' }),
  };
  const result = await fixture(client).resolveAzureDevOpsPermission('Project');
  assert.equal(result.role, 'admin');
  assert.equal(result.status, 'resolved');
});
test('SDK failure falls back to REST groups, not subjects', async () => {
  const urls = [];
  const client = { getDescriptor: async () => ({ value: 'aad.user' }), listMemberships: async () => { throw Error('sdk'); }, getGroup: async () => { throw Error('sdk'); } };
  const api = fixture(client, async url => {
    urls.push(url);
    return { ok: true, json: async () => url.includes('/groups/') ? { principalName: '[Project]\\HEI Managers' } : { value: url.includes('aad.user') ? [{ containerDescriptor: 'group' }] : [] } };
  });
  assert.equal((await api.resolveAzureDevOpsPermission('Project')).role, 'manager');
  assert.ok(urls.every(url => url.startsWith('https://vssps.dev.azure.com/example/_apis/graph/')));
  assert.ok(urls.some(url => url.includes('/groups/group')));
});
test('403 remains unverified and explains scope remediation', async () => {
  const client = { getDescriptor: async () => ({ value: 'aad.user' }), listMemberships: async () => { throw Error('sdk'); } };
  const result = await fixture(client, async () => ({ ok: false, status: 403 })).resolveAzureDevOpsPermission('Project');
  assert.equal(result.role, 'viewer');
  assert.equal(result.status, 'fallback');
  assert.match(result.warning, /403.*vso.graph/);
});
