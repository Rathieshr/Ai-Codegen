import { AzureDevOpsHostAdapter } from './AzureDevOpsHostAdapter';
import { HEIHostAdapter } from './HostAdapter';
import { StandaloneHostAdapter } from './StandaloneHostAdapter';

export * from './HostAdapter';

export function createHostAdapter(): HEIHostAdapter {
  const standalone = new URLSearchParams(window.location.search).get('host') === 'standalone';
  return standalone ? new StandaloneHostAdapter() : new AzureDevOpsHostAdapter();
}
