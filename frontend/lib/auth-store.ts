"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface OrganizationMembership {
  organization_id: string;
  organization_name: string;
  role: string;
}

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  memberships: OrganizationMembership[];
}

export type AuthStatus = "initializing" | "authenticated" | "unavailable";

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: AuthUser | null;
  activeOrganizationId: string | null;
  authStatus: AuthStatus;
  setTokens: (accessToken: string, refreshToken: string) => void;
  setUser: (user: AuthUser) => void;
  setActiveOrganization: (organizationId: string) => void;
  setAuthStatus: (status: AuthStatus) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      activeOrganizationId: null,
      authStatus: "initializing",
      setTokens: (accessToken, refreshToken) => set({ accessToken, refreshToken }),
      setUser: (user) =>
        set({
          user,
          activeOrganizationId: user.memberships[0]?.organization_id ?? null,
        }),
      setActiveOrganization: (organizationId) => set({ activeOrganizationId: organizationId }),
      setAuthStatus: (authStatus) => set({ authStatus }),
      logout: () =>
        set({ accessToken: null, refreshToken: null, user: null, activeOrganizationId: null }),
    }),
    {
      name: "gst-copilot-auth",
      partialize: ({ authStatus: _authStatus, ...state }) => state,
    }
  )
);
