import React from 'react';
import { HEIHostContext } from './host';

export function SettingsWorkspace({ context }: { context: HEIHostContext }) {
  return (
    <section className="hei-settings-workspace" aria-label="HEI Settings">
      <header><span>Administration</span><h2>Settings</h2><p>Host, workspace, and extension context for this HEI installation.</p></header>
      <div className="hei-settings-grid">
        <Group title="Azure DevOps Context"><Item label="Organization" value={context.organization.name} /><Item label="Project" value={context.project.name} /><Item label="Team" value={context.team.name} /><Item label="Sprint" value={context.sprint.name || context.sprint.path} /></Group>
        <Group title="Repository Context"><Item label="Repository" value={context.repository.name} /><Item label="Branch" value={context.repository.branch} /><Item label="Repository ID" value={context.repository.id} /></Group>
        <Group title="Host"><Item label="Host" value={context.hostType} /><Item label="Theme" value={context.theme} /><Item label="Extension" value={`${context.extension.publisherId}.${context.extension.id}`} /><Item label="Version" value={context.extension.version} /></Group>
        <Group title="Diagnostics"><Item label="Correlation ID" value={context.correlationId} /><Item label="User" value={context.user.name} /><Item label="Role" value={context.user.role} /></Group>
      </div>
    </section>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) { return <article><h3>{title}</h3>{children}</article>; }
function Item({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value || 'Not available'}</strong></div>; }
