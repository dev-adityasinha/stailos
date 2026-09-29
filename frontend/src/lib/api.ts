/** API client: bearer access token in memory/localStorage, automatic refresh
 *  on 401 (httpOnly refresh cookie), standard error envelope handling. */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/** Human-readable message for an ApiError, expanding field-level validation
 *  details (e.g. password policy) instead of the generic "Request validation
 *  failed" the 422 envelope carries as its top-level message. */
export function errorMessage(err: unknown, fallback = "Something went wrong."): string {
  if (!(err instanceof ApiError)) return fallback;
  if (err.code === "validation_error" && Array.isArray(err.details)) {
    const messages = (err.details as { msg?: string }[])
      .map((d) => d.msg)
      .filter((m): m is string => Boolean(m))
      .map((m) => m.replace(/^Value error,\s*/, ""));
    if (messages.length) return messages.join(" ");
  }
  return err.message;
}

const TOKEN_KEY = "pappu_access_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

let refreshPromise: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  refreshPromise ??= (async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (!res.ok) return false;
      const body = await res.json();
      setToken(body.data.access_token);
      return true;
    } catch {
      return false;
    } finally {
      setTimeout(() => (refreshPromise = null), 0);
    }
  })();
  return refreshPromise;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  formData?: FormData;
  params?: Record<string, string | number | boolean | undefined | null>;
  raw?: boolean; // return the Response (downloads)
}

export async function api<T = unknown>(
  path: string,
  options: RequestOptions = {},
  retried = false
): Promise<T> {
  const { method = "GET", body, formData, params, raw } = options;
  const url = new URL(`${API_BASE}${path}`);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
    }
  }
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(url, {
    method,
    headers,
    credentials: "include",
    body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
  });

  if (res.status === 401 && !retried && !path.startsWith("/auth/login")) {
    if (await tryRefresh()) return api<T>(path, options, true);
    setToken(null);
    if (typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
      location.href = "/login";
    }
  }

  if (raw) {
    if (!res.ok) throw new ApiError(res.status, "download_failed", "Download failed");
    return res as unknown as T;
  }

  const text = await res.text();
  const json = text ? JSON.parse(text) : {};
  if (!res.ok) {
    const err = json?.error ?? {};
    throw new ApiError(
      res.status,
      err.code ?? "error",
      err.message ?? `Request failed (${res.status})`,
      err.details
    );
  }
  return json as T;
}

/** Trigger a browser download from an authenticated endpoint. */
export async function downloadFile(
  path: string,
  options: RequestOptions = {},
  fallbackName = "download"
) {
  const res = await api<Response>(path, { ...options, raw: true });
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") ?? "";
  const match = /filename="?([^";]+)"?/.exec(disposition);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = match?.[1] ?? fallbackName;
  a.click();
  URL.revokeObjectURL(a.href);
}
