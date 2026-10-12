// All calls to the backend. Start the backend with backend\run_api.bat first.
export const API_URL = "http://localhost:8000";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(API_URL + path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new ApiError("Can't reach the API. Double-click backend\\run_api.bat and keep that window open.", 0);
  }
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = "Some fields are missing or invalid.";
    } catch {
      // no JSON body
    }
    const fallback = res.status === 404 ? "Not found." : `The API returned an error (${res.status}).`;
    throw new ApiError(detail && detail !== "Not Found" ? detail : fallback, res.status);
  }
  return res.status === 204 ? null : res.json();
}

const json = (body) => ({ body: JSON.stringify(body) });

// Organizations (clients)
export const getOrganizations = () => request("/organizations");
export const addOrganization = (data) => request("/organizations", { method: "POST", ...json(data) });
export const deleteOrganization = (orgId) => request(`/organizations/${orgId}`, { method: "DELETE" });

// Accounts: ours and competitors', on RSS or YouTube
export const getAccounts = (orgId) => request(`/organizations/${orgId}/accounts`);
export const addAccount = (orgId, data) => request(`/organizations/${orgId}/accounts`, { method: "POST", ...json(data) });
export const deleteAccount = (orgId, id) => request(`/organizations/${orgId}/accounts/${id}`, { method: "DELETE" });

// YouTube channels matching what the user types (logo, name, handle, subscribers)
export const suggestChannels = (q) => request(`/youtube/suggest?q=${encodeURIComponent(q)}`);

// Refresh and results
export const fetchNews = (orgId) => request(`/organizations/${orgId}/fetch`, { method: "POST" });
export const getResults = (orgId) => request(`/organizations/${orgId}/results`);

// Formatting helpers
export function toIST(iso) {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function compact(n) {
  if (n === null || n === undefined) return "–";
  return new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function duration(seconds) {
  if (!seconds) return "–";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h) return `${h}h ${m}m`;
  return m ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}

export const PLATFORM_LABEL = { rss: "Website", youtube: "YouTube" };
