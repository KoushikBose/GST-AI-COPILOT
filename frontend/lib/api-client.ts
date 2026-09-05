import axios, { type AxiosInstance } from "axios";
import { useAuthStore } from "@/lib/auth-store";

/**
 * Central HTTP client for the backend API. Attaches the bearer token and
 * active-organization header from the auth store on every request, so
 * call sites never have to thread auth state through manually.
 */
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const apiClient: AxiosInstance = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  timeout: 60_000,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use((config) => {
  const { accessToken, activeOrganizationId } = useAuthStore.getState();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  if (activeOrganizationId) {
    config.headers["X-Organization-ID"] = activeOrganizationId;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
    }
    return Promise.reject(error);
  }
);

export interface ApiErrorBody {
  success: false;
  error: {
    code: string;
    message: string;
    request_id: string;
  };
}

export function isApiErrorBody(data: unknown): data is ApiErrorBody {
  return (
    typeof data === "object" &&
    data !== null &&
    "success" in data &&
    (data as { success: unknown }).success === false
  );
}

export function getApiErrorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (axios.isAxiosError(error) && isApiErrorBody(error.response?.data)) {
    return error.response!.data.error.message;
  }
  return fallback;
}

export interface ChatStreamEvent {
  type: "session" | "intent" | "delta" | "done" | "error";
  session_id?: string;
  message_id?: string;
  intent?: string;
  text?: string;
  answer?: string;
  citations?: unknown[];
  confidence?: number;
  requires_human_review?: boolean;
  calculations?: Record<string, unknown> | null;
  message?: string;
}

/**
 * Consumes the `POST /chat/stream` server-sent-event response. Axios can't
 * surface a streaming body in the browser, so this goes through `fetch`
 * directly while still borrowing the auth headers from the store. `onEvent`
 * is called once per decoded SSE `data:` line.
 */
export async function streamChat(
  body: { message: string; session_id?: string | null },
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const { accessToken, activeOrganizationId } = useAuthStore.getState();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (activeOrganizationId) headers["X-Organization-ID"] = activeOrganizationId;

  const res = await fetch(`${API_BASE_URL}/api/v1/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal,
  });

  if (res.status === 401) {
    useAuthStore.getState().logout();
    throw new Error("Your session expired. Please reload.");
  }
  if (!res.ok || !res.body) {
    throw new Error(`Chat stream failed (${res.status}).`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()) as ChatStreamEvent);
      } catch {
        // ignore a partial/garbled frame — the next read will resync
      }
    }
  }
}
