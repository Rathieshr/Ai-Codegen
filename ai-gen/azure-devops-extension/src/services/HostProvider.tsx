import * as React from 'react';
import * as SDK from 'azure-devops-extension-sdk';
import { IWorkItemLoadedArgs } from 'azure-devops-extension-api/WorkItemTracking/WorkItemTrackingServices';

export interface HostContextType {
  isReady: boolean;
  workItemId?: number;
  projectName?: string;
  user?: { name: string; email?: string };
}

export const HostContext = React.createContext<HostContextType>({ isReady: false });

export function useHostProvider() {
  return React.useContext(HostContext);
}

export interface HostProviderProps {
  children: React.ReactNode;
}

export function HostProvider({ children }: HostProviderProps) {
  const [contextState, setContextState] = React.useState<HostContextType>({ isReady: false });

  React.useEffect(() => {
    let isMounted = true;

    async function initSDK() {
      try {
        await SDK.init({ loaded: false, applyTheme: true });
        await SDK.ready();

        if (!isMounted) return;

        const user = SDK.getUser();
        
        // Register for Work Item events if we are on a work item form
        SDK.register(SDK.getContributionId(), () => {
          return {
            onLoaded: (args: IWorkItemLoadedArgs) => {
              if (isMounted) {
                setContextState(prev => ({ ...prev, workItemId: args.id }));
              }
            }
          };
        });

        SDK.notifyLoadSucceeded();

        setContextState({
          isReady: true,
          user: { name: user.displayName, email: user.name }
        });
      } catch (err) {
        console.error("Failed to initialize ADO SDK", err);
      }
    }

    initSDK();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <HostContext.Provider value={contextState}>
      {children}
    </HostContext.Provider>
  );
}
