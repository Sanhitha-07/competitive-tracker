import { useEffect, useState } from "react";
import { ago, createOpportunity, fmtTime, getTrends, refreshTrends } from "../api";
import { PostMini } from "../components/Evidence";

const ACTION = {
  go: { tone: "good", icon: "✓" },
  care: { tone: "warn", icon: "!" },
  avoid: { tone: "bad", icon: "✕" },
};
const FILTERS = [
  ["all", "All"], ["go", "Good to join"], ["care", "With care"], ["avoid", "Avoid"], ["rising", "Rising"], ["early", "Be first"],
];

// Sensitivity + what it means for this workspace, always as icon + words (never colour alone).
export function SensitivityBadge({ t }) {
  const a = ACTION[t.advice.action];
  const why = t.sensitivity.labels.length ? ` (${t.sensitivity.labels.join(", ")})` : "";
  return (
    <span className={`pill ${a.tone} tiny`} title={`${t.advice.advice}${why}`}>
      {a.icon} {t.advice.label}
    </span>
  );
}

function TrendCard({ t, orgId }) {
  const [msg, setMsg] = useState("");
  async function save() {
    try {
      await createOpportunity(orgId, t.key, "save");
      setMsg("Saved to Opportunities.");
    } catch (e) {
      setMsg(e.message);
    }
  }
  return (
    <article className={`trend-card ${t.advice.action}`}>
      {t.picture && <img src={t.picture} alt="" className="trend-pic" loading="lazy" />}
      <div className="trend-body">
        <div className="trend-head">
          <span className="kind">{t.source_label}{t.also_from ? ` + ${t.also_from.join(", ")}` : ""}</span>
          <div className="chips">
            {t.rising && <span className="pill good tiny">▲ rising</span>}
            <SensitivityBadge t={t} />
          </div>
        </div>
        <h3>{t.link ? <a href={t.link} target="_blank" rel="noreferrer">{t.title}</a> : t.title}</h3>
        <p className="small"><span className="lbl">Signal:</span> {t.signal}</p>
        <p className="small"><span className="lbl">Why it's relevant:</span> {t.why_relevant}</p>
        <p className="small"><span className="lbl">Competitors:</span> {t.coverage.text}</p>
        {t.advice.action !== "go" && (
          <p className={`small advice ${t.advice.action}`}>
            <b>{t.advice.label}.</b> {t.advice.advice}
            {t.sensitivity.labels.length > 0 && <span className="muted"> Flagged for: {t.sensitivity.labels.join(", ").toLowerCase()} ({t.sensitivity.matched.join(", ")}).</span>}
          </p>
        )}
        {t.angles.length > 0 && (
          <div>
            <span className="lbl small">Angles you could take:</span>
            <ul className="angles">{t.angles.map((a) => <li key={a}>{a}</li>)}</ul>
          </div>
        )}
        {(t.related.length > 0 || t.coverage.posts.length > 0) && (
          <details className="evidence">
            <summary>Sources and matching posts</summary>
            {t.related.length > 0 && (
              <ul className="limits">
                {t.related.map((r, i) => (
                  <li key={i}>
                    <a href={r.link} target="_blank" rel="noreferrer">{r.title}</a>
                    <span className="muted small"> {r.source || ""}{r.published_at ? ` · ${fmtTime(r.published_at)}` : ""}</span>
                  </li>
                ))}
              </ul>
            )}
            {t.coverage.posts.length > 0 && <div className="post-mini-list" style={{ marginTop: 8 }}>{t.coverage.posts.map((p) => <PostMini key={p.id} p={p} />)}</div>}
          </details>
        )}
        {t.advice.action !== "avoid" && (
          <div className="card-actions">
            <button className="btn ghost small-btn" onClick={save}>Save as opportunity</button>
            {msg && <span className="muted small">{msg}</span>}
          </div>
        )}
      </div>
    </article>
  );
}

export default function Trends({ orgId, refreshKey }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  async function load() {
    try {
      setData(await getTrends(orgId));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, refreshKey]);

  async function refresh() {
    setBusy(true);
    setNote("");
    try {
      const r = await refreshTrends(orgId);
      const failed = (r.sources || []).filter((s) => !s.ok);
      setNote(`Checked ${(r.sources || []).length} source${r.sources?.length === 1 ? "" : "s"}.` +
        (failed.length ? ` Couldn't read: ${failed.map((s) => `${s.source} (${s.error})`).join("; ")}` : ""));
      await load();
    } catch (e) {
      setNote(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <section className="panel"><div className="empty"><b>Trends not available</b><span>{error}</span></div></section>;
  if (!data) return <section className="panel"><div className="empty"><b>Loading trends…</b></div></section>;

  const items = data.trends.filter((t) =>
    filter === "all" ? true : filter === "rising" ? t.rising
      : filter === "early" ? t.advice.action !== "avoid" && !t.coverage.competitors.length && !t.coverage.yours
        : t.advice.action === filter);
  const count = (f) => data.trends.filter((t) => (f === "rising" ? t.rising : f === "early"
    ? t.advice.action !== "avoid" && !t.coverage.competitors.length && !t.coverage.yours : f === "all" || t.advice.action === f)).length;
  const off = Object.entries(data.sources).filter(([, on]) => !on).map(([k]) => k.replace("_", " "));

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Trends</h2>
          <p className="muted">
            What people are searching for and reading about in {data.config.region_label}, matched to your workspace and compared with what your competitors posted this week.
            Rated for your brand-safety setting: <b>{data.config.brand_safety_label}</b>.
          </p>
          <p className="muted small">Last checked {ago(data.last_refresh)}.{off.length > 0 && ` Switched off: ${off.join(", ")}.`}</p>
        </div>
        <button className="btn primary small-btn" onClick={refresh} disabled={busy}>{busy ? "Checking…" : "↻ Check trends now"}</button>
      </div>
      {note && <div className="notice small">{note}</div>}

      <div className="chips" role="tablist" aria-label="Filter trends">
        {FILTERS.map(([id, label]) => (
          <button key={id} className={`chip ${filter === id ? "on" : ""}`} onClick={() => setFilter(id)}>
            {label} <span className="chip-count">{count(id)}</span>
          </button>
        ))}
      </div>

      {items.length === 0 ? (
        <div className="empty">
          <b>{data.trends.length ? "Nothing in this filter" : "No matching trends yet"}</b>
          <span>Trends are matched with your workspace topics, niche, audience and industry. Add a few topics in Workspace settings, then click "Check trends now".</span>
        </div>
      ) : (
        <div className="trend-list">{items.map((t) => <TrendCard key={t.key} t={t} orgId={orgId} />)}</div>
      )}
      <p className="muted small">{data.method}</p>
    </section>
  );
}
