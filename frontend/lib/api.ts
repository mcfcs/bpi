// Empty by default: requests go to /api/* on the same origin and Next proxies them to the backend
// (next.config.mjs). Set NEXT_PUBLIC_API_URL only to call a backend on another origin directly.
const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
const TOKEN_KEY = "si-evidence:token";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage can be unavailable (private windows); the session then lasts for this page only.
  }
}

async function request(path: string, init: RequestInit & { json?: unknown } = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers, body });
  } catch {
    throw new ApiError(0, `Cannot reach the evidence service${BASE ? ` at ${BASE}` : ""}. Is the backend running?`);
  }
  if (!response.ok) {
    let detail: unknown = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      // Not JSON: when the backend is down, the Next proxy answers with a bare 5xx.
      if (response.status >= 500) detail = "The evidence service is not responding. Is the backend running?";
    }
    const message = typeof detail === "string" ? detail : Array.isArray(detail)
      ? detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ")
      : "The request failed.";
    throw new ApiError(response.status, message || "The request failed.");
  }
  return response;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  return (await request(path, init)).json() as Promise<T>;
}

/** Fetch an authenticated file and hand it to the browser as a download. */
export async function download(path: string, filename: string): Promise<void> {
  const blob = await (await request(path)).blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/**
 * Open a study's report PDF in a new tab at `page` (page 1 when the finding has no page).
 *
 * The PDF endpoint needs the Bearer token, which a plain link cannot send, so the backend issues a
 * two-minute signed link instead. The tab is opened during the click, before the link is fetched,
 * so pop-up blockers treat it as the user's own action; it is pointed at the PDF once the link
 * arrives, and closed again if the study turns out to be unreadable.
 */
export async function openReport(studyId: string, page?: number | null): Promise<void> {
  const tab = window.open("", "_blank");
  if (tab) {
    tab.document.title = "Opening the report…";
    tab.document.body.style.font = "16px system-ui, sans-serif";
    tab.document.body.textContent = "Opening the report…";
  }
  try {
    const { url } = await api<{ url: string }>(
      `/api/studies/${encodeURIComponent(studyId)}/document/link?page=${page && page > 0 ? page : 1}`,
      { method: "POST" },
    );
    // Absolute, because the blank tab has no base URL of its own to resolve a path against.
    const href = new URL(`${BASE}${url}`, window.location.href).href;
    if (tab) {
      tab.opener = null;
      tab.location.href = href;
    } else if (!window.open(href, "_blank", "noopener")) {
      throw new ApiError(0, "Your browser blocked the new tab. Allow pop-ups for this site to open reports.");
    }
  } catch (e) {
    tab?.close();
    throw e;
  }
}
