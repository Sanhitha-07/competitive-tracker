// All calls to the backend. Start the backend with backend\run_api.bat first.
// 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 first, and the API only listens on IPv4.
export const API_URL = "http://127.0.0.1:8000";

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
const qs = (params) => {
  const s = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "" && v !== false) s.set(k, v);
  });
  const out = s.toString();
  return out ? `?${out}` : "";
};

// Form choices (creator types, industries, goals, formats) and what each platform can measure
export const getOptions = () => request("/meta/options");

// Organizations (workspaces) and their configuration
export const getOrganizations = () => request("/organizations");
export const addOrganization = (data) => request("/organizations", { method: "POST", ...json(data) });
export const deleteOrganization = (orgId) => request(`/organizations/${orgId}`, { method: "DELETE" });
export const getConfig = (orgId) => request(`/organizations/${orgId}/config`);
export const saveConfig = (orgId, data) => request(`/organizations/${orgId}/config`, { method: "PUT", ...json(data) });

// Accounts: ours and competitors', on any supported platform
export const getAccounts = (orgId) => request(`/organizations/${orgId}/accounts`);
export const addAccount = (orgId, data) => request(`/organizations/${orgId}/accounts`, { method: "POST", ...json(data) });
export const deleteAccount = (orgId, id) => request(`/organizations/${orgId}/accounts/${id}`, { method: "DELETE" });

// YouTube channels matching what the user types (logo, name, handle, subscribers)
export const suggestChannels = (q) => request(`/youtube/suggest?q=${encodeURIComponent(q)}`);

// Refresh and results
export const fetchNews = (orgId) => request(`/organizations/${orgId}/fetch`, { method: "POST" });
export const getResults = (orgId) => request(`/organizations/${orgId}/results`);
export const getTopics = (orgId) => request(`/organizations/${orgId}/topics`);
export const getContent = (orgId, filters) => request(`/organizations/${orgId}/content${qs(filters)}`);
export const getHistory = (orgId, days = 90) => request(`/organizations/${orgId}/history?days=${days}`);
export const getPostHistory = (orgId, postId) => request(`/organizations/${orgId}/posts/${postId}/history`);

// Opportunities: recommendation -> brief -> MediaOps draft -> scheduled -> published -> evaluated
const opp = (orgId, id = "") => `/organizations/${orgId}/opportunities${id !== "" ? `/${id}` : ""}`;
export const getOpportunities = (orgId) => request(opp(orgId));
export const createOpportunity = (orgId, key, action = "save") =>
  request(opp(orgId), { method: "POST", ...json({ key, action }) });
export const updateOpportunity = (orgId, id, data) => request(opp(orgId, id), { method: "PATCH", ...json(data) });
export const regenerateBrief = (orgId, id) => request(`${opp(orgId, id)}/brief`, { method: "POST" });
export const sendToMediaOps = (orgId, id, platforms) =>
  request(`${opp(orgId, id)}/mediaops`, { method: "POST", ...json({ platforms }) });
export const evaluateOpportunity = (orgId, id) => request(`${opp(orgId, id)}/evaluate`, { method: "POST" });
export const calendarUrl = (orgId, id) => `${API_URL}${opp(orgId, id)}/calendar.ics`;

// ---- Formatting helpers ----

// Times are shown in the workspace's time zone (set from its configuration).
let displayTimeZone = "Asia/Kolkata";
export function setDisplayTimeZone(tz) {
  displayTimeZone = tz || "Asia/Kolkata";
}
export function tzLabel() {
  return displayTimeZone;
}

export function fmtTime(iso) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString("en-IN", {
      timeZone: displayTimeZone, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return new Date(iso).toLocaleString();
  }
}
export const toIST = fmtTime; // older name, kept for existing pages

export function fmtDate(iso) {
  if (!iso) return "-";
  return new Date(iso).toLocaleDateString("en-IN", { timeZone: displayTimeZone, day: "2-digit", month: "short", year: "numeric" });
}

export function ago(iso) {
  if (!iso) return "never";
  const h = (Date.now() - new Date(iso).getTime()) / 3600000;
  if (h < 1) return "just now";
  if (h < 48) return `${Math.round(h)}h ago`;
  return `${Math.round(h / 24)} days ago`;
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

export function period(hours) {
  if (!hours) return "recently";
  return hours >= 48 ? `the last ${Math.round(hours / 24)} days` : `the last ${hours} hours`;
}

export const PLATFORM_LABEL = { rss: "Website", youtube: "YouTube" };
export const FORMAT_LABEL = {
  short: "Short", video: "Video", long: "Long-form", live: "Live stream", article: "Article",
  image: "Image", podcast: "Podcast", newsletter: "Newsletter",
};
export const STATUS_LABEL = {
  saved: "Saved", brief: "Brief ready", in_mediaops: "In MediaOps", scheduled: "Scheduled",
  published: "Published", evaluated: "Measured", dismissed: "Dismissed",
};
