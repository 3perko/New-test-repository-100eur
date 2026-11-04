// Thin fetch wrapper: cookies for auth, active company header, Slovak error messages.

let activeCompany: number | null = null;
export function setActiveCompany(id: number | null) {
  activeCompany = id;
}
export function getActiveCompany() {
  return activeCompany;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function headers(json: boolean): Record<string, string> {
  const h: Record<string, string> = { "X-Requested-With": "app" };
  if (json) h["Content-Type"] = "application/json";
  if (activeCompany) h["X-Company-Id"] = String(activeCompany);
  return h;
}

async function handle<T>(r: Response): Promise<T> {
  if (r.status === 401 && !location.pathname.startsWith("/prihlasenie")) {
    location.href = "/prihlasenie";
    throw new ApiError(401, "Neprihlásený");
  }
  if (!r.ok) {
    let msg = `Chyba ${r.status}`;
    try {
      const j = await r.json();
      if (typeof j.detail === "string") msg = j.detail;
      else if (Array.isArray(j.detail)) msg = j.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* ignore */
    }
    throw new ApiError(r.status, msg);
  }
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/json")) return (await r.json()) as T;
  return (await r.text()) as unknown as T;
}

export type Params = Record<string, string | number | boolean | null | undefined>;

export function qs(params?: Params): string {
  if (!params) return "";
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

export const api = {
  get: <T,>(url: string, params?: Params) =>
    fetch(url + qs(params), { headers: headers(false), credentials: "same-origin" }).then((r) => handle<T>(r)),
  post: <T,>(url: string, body?: unknown) =>
    fetch(url, { method: "POST", headers: headers(true), body: JSON.stringify(body ?? {}), credentials: "same-origin" }).then(
      (r) => handle<T>(r),
    ),
  put: <T,>(url: string, body?: unknown) =>
    fetch(url, { method: "PUT", headers: headers(true), body: JSON.stringify(body ?? {}), credentials: "same-origin" }).then(
      (r) => handle<T>(r),
    ),
  patch: <T,>(url: string, body?: unknown) =>
    fetch(url, { method: "PATCH", headers: headers(true), body: JSON.stringify(body ?? {}), credentials: "same-origin" }).then(
      (r) => handle<T>(r),
    ),
  del: <T,>(url: string) =>
    fetch(url, { method: "DELETE", headers: headers(false), credentials: "same-origin" }).then((r) => handle<T>(r)),
  upload: <T,>(url: string, form: FormData) =>
    fetch(url, { method: "POST", headers: headers(false), body: form, credentials: "same-origin" }).then((r) => handle<T>(r)),
};

/** URL usable in <a href> / window.open (no custom headers possible) */
export function linkUrl(url: string, params?: Params): string {
  return url + qs({ ...(params || {}), _company: activeCompany ?? undefined });
}
