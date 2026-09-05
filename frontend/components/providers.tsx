"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { AutoAuth } from "@/components/auto-auth";

/**
 * Global client-side providers: React Query for server-state, silent
 * auto-auth (see components/auto-auth.tsx), and the mount point for future
 * providers (theme, toast).
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AutoAuth />
      {children}
    </QueryClientProvider>
  );
}
