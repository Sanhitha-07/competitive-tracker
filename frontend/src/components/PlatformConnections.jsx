import { useCallback, useEffect, useState } from "react";
import { choosePage, connectPlatform, disconnectPlatform, fmtDate, getIntegrations, NOT_CONFIGURED_TEXT } from "../api";
import PlatformIcon from "./PlatformIcon";
import Popup from "./Popup";

// Status shown per platform. "Connected" comes only from the server, after a real sign-in succeeded.
const STATE = {
  not_configured: ["neutral", "Not configured"],
  not_connected: ["warn", "Not connected"],
  needs_page: ["warn", "Choose a Page"],
  connected: ["good", "Connected"],
  expired: ["bad", "Expired"],
  error: ["bad", "Couldn't connect"],
  revoked: ["bad", "Access removed"],
};

function PageChooser({ orgId, p, onDone }) {
  const [pageId, setPageId] = useState(p.connection.choices[0]?.id || "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      await choosePage(orgId, p.id, pageId);
      onDone();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="inline-form">
      <select value={pageId} onChange={(e) => setPageId(e.target.value)} aria-label={`${p.label} Page`}>
        {p.connection.choices.map((c) => (
          <option key={c.id} value={c.id}>{c.name}{p.id === "instagram" && c.instagram ? ` (@${c.instagram.username})` : ""}</option>
        ))}
      </select>
      <button className="btn primary small-btn" onClick={save} disabled={busy || !pageId}>Use this Page</button>
      {error && <span className="error-text small">{error}</span>}
    </div>
  );
}

function statusText(p) {
  const c = p.connection;
  if (p.state === "not_configured") return NOT_CONFIGURED_TEXT;
  if (p.state === "connected" && c) return `Connected as ${c.username ? `@${c.username}` : c.account_name} · since ${fmtDate(c.connected_at)}`;
  if (p.state === "needs_page") return "Signed in. Choose which Page this workspace uses.";
  if (p.state === "expired") return "Access expired. Reconnect to keep collecting posts.";
  if (p.state === "error" || p.state === "revoked") return c?.last_error || "Reconnect to try again.";
  return "Not connected to this workspace.";
}

// Instagram, Facebook and X: connection status and actions for this workspace.
// Setup instructions for developers live in SOCIAL_SETUP.md, not in the app.
export default function PlatformConnections({ orgId, onChanged }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [confirm, setConfirm] = useState(null);
  const [blocked, setBlocked] = useState(""); // platform whose Connect was clicked without credentials

  const load = useCallback(async () => {
    try {
      setData(await getIntegrations(orgId));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, [orgId]);
  useEffect(() => { load(); }, [load]);

  async function connect(p) {
    setBusy(p.id);
    try {
      const { authorize_url: url } = await connectPlatform(orgId, p.id);
      window.location.assign(url); // the platform's own sign-in page; it sends the user back here
    } catch (e) {
      setError(e.message);
      setBusy("");
    }
  }
  async function disconnect(p) {
    try {
      await disconnectPlatform(orgId, p.id);
      setConfirm(null);
      await load();
      onChanged?.();
    } catch (e) {
      setError(e.message);
    }
  }

  if (!data) return error ? <p className="error-text">{error}</p> : null;
  return (
    <div className="connections">
      <h3 className="sub-head">Platform connections</h3>
      {error && <p className="error-text small" role="alert">{error}</p>}
      <ul className="conn-list">
        {data.platforms.map((p) => {
          const [tone, label] = STATE[p.state] || ["neutral", "Unknown"];
          const signedIn = ["connected", "needs_page", "expired", "error", "revoked"].includes(p.state);
          return (
            <li key={p.id} className="conn-row">
              <div className="conn-main">
                <PlatformIcon platform={p.id} size={22} />
                <div className="conn-text">
                  <div className="conn-title">
                    <b>{p.label}</b>
                    <span className={`pill tiny ${tone}`}>{label}</span>
                  </div>
                  <span className="muted small">{statusText(p)}</span>
                </div>
              </div>
              <div className="row-actions conn-actions">
                {p.state === "not_configured" && (
                  // No sign-in is started (and no request sent) without credentials: explain instead.
                  <button className="btn ghost small-btn conn-unavailable" aria-describedby={`conn-msg-${p.id}`}
                    onClick={() => setBlocked((b) => (b === p.id ? "" : p.id))}>
                    Connect
                  </button>
                )}
                {p.state === "not_connected" && (
                  <button className="btn primary small-btn" onClick={() => connect(p)} disabled={busy === p.id}>
                    {busy === p.id ? "Opening…" : "Connect"}
                  </button>
                )}
                {signedIn && (
                  <>
                    <button className={`btn small-btn ${p.state === "connected" ? "ghost" : "primary"}`} onClick={() => connect(p)} disabled={busy === p.id}>
                      {busy === p.id ? "Opening…" : "Reconnect"}
                    </button>
                    <button className="btn ghost small-btn" onClick={() => setConfirm(p)}>Disconnect</button>
                  </>
                )}
              </div>
              {blocked === p.id && p.state === "not_configured" && (
                <div className="conn-extra conn-blocked" id={`conn-msg-${p.id}`} role="status">
                  <span className="small">{p.label} can't be connected until it's configured. Contact your administrator to enable it.</span>
                  <button className="link-btn small" onClick={() => setBlocked("")}>OK</button>
                </div>
              )}
              {p.state === "needs_page" && p.connection?.choices?.length > 0 && (
                <div className="conn-extra">
                  <PageChooser orgId={orgId} p={p} onDone={() => { load(); onChanged?.(); }} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {confirm && (
        <Popup title={`Disconnect ${confirm.label}?`} onClose={() => setConfirm(null)}>
          <p>The tracker stops collecting new {confirm.label} posts for this workspace. Posts already collected stay.</p>
          <div className="popup-actions">
            <button className="btn ghost" onClick={() => setConfirm(null)}>Cancel</button>
            <button className="btn danger" onClick={() => disconnect(confirm)}>Disconnect</button>
          </div>
        </Popup>
      )}
    </div>
  );
}
