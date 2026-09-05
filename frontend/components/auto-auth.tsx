"use client";

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/lib/auth-store";

/**
 * Silently authenticates the browser against a single fixed demo account —
 * there is no login/register UI (removed by design), so this is the only
 * way the app ever gets a bearer token. Login first; if the account doesn't
 * exist yet, register it (idempotent from the user's point of view: same
 * account every time, on every browser, until the backend's demo user is
 * reset). Nothing is rendered; it just populates the auth store, then lets
 * React Query refetch whatever was waiting on it.
 *
 * This exists purely to make the demo usable without a login screen — it is
 * not a real multi-user auth flow. Swap it for actual login UI before this
 * ever serves real users.
 */
const DEMO_EMAIL = "demo@gst-copilot.app";
const DEMO_PASSWORD = "GstCopilotDemo#2026";
const DEMO_ORG_NAME = "Demo Organization";
const DEMO_FULL_NAME = "Demo User";

export function AutoAuth() {
  const queryClient = useQueryClient();
  const { accessToken, setTokens, setUser, setAuthStatus, logout } = useAuthStore();
  const attempted = useRef(false);

  useEffect(() => {
    if (attempted.current) return;
    attempted.current = true;

    (async () => {
      try {
        let tokens: { access_token: string; refresh_token: string } | null = null;

        if (accessToken) {
          try {
            const me = await apiClient.get("/auth/me");
            setUser(me.data);
            setAuthStatus("authenticated");
            return;
          } catch {
            // A persisted token may have expired. Continue with the demo
            // bootstrap rather than leaving protected API calls at 401.
          }
        }

        try {
          const { data } = await apiClient.post("/auth/login", {
            email: DEMO_EMAIL,
            password: DEMO_PASSWORD,
          });
          tokens = data;
        } catch (err) {
          // 401 here means "no such account" (see AuthService.authenticate) —
          // create it once. Any other status is a real problem; don't paper
          // over it by attempting a registration that will just fail too.
          if (axios.isAxiosError(err) && err.response?.status === 401) {
            const { data } = await apiClient.post("/auth/register", {
              full_name: DEMO_FULL_NAME,
              organization_name: DEMO_ORG_NAME,
              email: DEMO_EMAIL,
              password: DEMO_PASSWORD,
            });
            tokens = data;
          } else {
            throw err;
          }
        }

        if (!tokens) throw new Error("Demo authentication did not return tokens.");
        setTokens(tokens.access_token, tokens.refresh_token);

        const me = await apiClient.get("/auth/me", {
          headers: { Authorization: `Bearer ${tokens.access_token}` },
        });
        setUser(me.data);
        setAuthStatus("authenticated");

        // Everything that rendered while unauthenticated (401s) should retry now.
        await queryClient.invalidateQueries();
      } catch (err) {
        // Backend unreachable or genuinely misconfigured — the sidebar's API
        // status pill already surfaces that; nothing more to do here.
        console.warn("auto-auth failed", err);
        logout();
        setAuthStatus("unavailable");
      }
    })();
  }, [accessToken, queryClient, setTokens, setUser, setAuthStatus, logout]);

  return null;
}
