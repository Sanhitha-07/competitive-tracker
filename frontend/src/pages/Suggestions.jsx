import { useEffect, useState } from "react";
import { createOpportunity, fmtDate, getChanges, PRIORITY_TONE, updateChange } from "../api";
import Evidence, { ConfidencePill, PostMini } from "../components/Evidence";
import { BriefButton, Empty, Loading, PageHead } from "../components/ui";

const KINDS = [
  { id: "all", label: "All" },
  { id: "topic_gap", label: "Topics" },
  { id: "audience_question", label: "Audience questions" },
  { id: "outlier", label: "Standout competitor posts" },
  { id: "format_test", label: "Formats to test" },
  { id: "publishing_pattern", label: "Publishing patterns" },
  { id: "benchmark", label: "Benchmarks" },
];
const FIRST_SHOWN = 8; // the strongest first; the rest on request, so the page stays readable
const CHANGE_KIND = { frequency: "Publishing rhythm", format: "New format", standout: "Standout post", topic: "New topic", audience: "Audience" };

export function Readiness({ items, onNavigate }) {
  if (!items?.length) return null;
  return (
    <div className="readiness">
      <b>Missing data: these would make suggestions more reliable</b>
      <ul>{items.map((n) => <li key={n}>{n}</li>)}</ul>
      <div className="chips">
        <button className="btn ghost small-btn" onClick={() => onNavigate("workspace")}>Workspace settings</button>
        <button className="btn ghost small-btn" onClick={() => onNavigate("accounts")}>Accounts</button>
      </div>
    </div>
  );
}

export function PriorityPill({ priority }) {
  if (!priority) return null;
  return (
    <span className={`pill ${PRIORITY_TONE[priority.level]}`} title={`Why: ${priority.reasons.join("; ")}`}>
      {priority.level[0].toUpperCase() + priority.level.slice(1)} priority
    </span>
  );
}

function period(rec) {
  const dp = rec.data_period;
  if (!dp) return null;
  if (dp.from && dp.to) return `${fmtDate(dp.from)} – ${fmtDate(dp.to)}`;
  if (dp.days) return `last ${dp.days} days`;
  return null;
}

export function RecCard({ rec, actions }) {
  return (
    <article className={`sugg ${rec.tone}`}>
      <div className="sugg-head">
        <span className="kind">{rec.kind_label}</span>
        <span className="pills">
          <PriorityPill priority={rec.priority} />
          <ConfidencePill confidence={rec.confidence} />
        </span>
      </div>
      <b className="sugg-title">{rec.title}</b>
      <p><span className="lbl">What we saw (data):</span> {rec.observed}</p>
      <p><span className="lbl">Why it may matter (our reading):</span> {rec.why_relevant}</p>
      {rec.suggested_format_label && <p><span className="lbl">Suggested format:</span> {rec.suggested_format_label}</p>}
      <p><span className="lbl">Next step:</span> {rec.next_step}</p>
      {rec.related_topics?.length > 0 && <p className="muted small">Related topics: {rec.related_topics.join(", ")}</p>}
      <p className="meta-line small">
        {period(rec) && <span>Period: {period(rec)}</span>}
        {rec.sample?.text && <span>Sample: {rec.sample.text}</span>}
      </p>
      {rec.priority && (
        <details className="why-priority small">
          <summary>Why {rec.priority.level} priority?</summary>
          <ul>{rec.priority.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </details>
      )}
      <Evidence rec={rec} />
      {actions}
    </article>
  );
}

function ChangeFeed({ orgId, refreshKey, onNavigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [show, setShow] = useState("new");

  useEffect(() => {
    let cancelled = false;
    getChanges(orgId)
      .then((d) => !cancelled && (setData(d), setError("")))
      .catch((e) => !cancelled && setError(e.message));
    return () => { cancelled = true; };
  }, [orgId, refreshKey]);

  async function mark(c, status) {
    try {
      const updated = await updateChange(orgId, c.id, status);
      setData((d) => ({
        ...d,
        changes: d.changes.map((x) => (x.id === c.id ? updated : x)),
        counts: { ...d.counts, [c.status]: d.counts[c.status] - 1, [status]: d.counts[status] + 1 },
      }));
    } catch (e) {
      setError(e.message);
    }
  }

  const list = (data?.changes || []).filter((c) => show === "all" || c.status === show);
  return (
    <section className="panel">
      <PageHead
        title="What changed at competitors"
        what="Notable changes in competitors' public posts and numbers, found after each Refresh. Each change is listed once."
        next="Mark a change as reviewed, save it, or act on it."
      >
        <div className="segmented small" role="tablist" aria-label="Show changes">
          {[["new", "New"], ["saved", "Saved"], ["reviewed", "Reviewed"], ["all", "All"]].map(([id, label]) => (
            <button key={id} role="tab" aria-selected={show === id} className={show === id ? "on" : ""} onClick={() => setShow(id)}>
              {label}{data && id !== "all" ? ` (${data.counts[id]})` : ""}
            </button>
          ))}
        </div>
      </PageHead>
      {error ? <p className="error-text">{error}</p> : !data ? <Loading what="Checking for changes…" /> : list.length === 0 ? (
        <p className="muted">{show === "new" ? "No new changes. They appear here after a Refresh collects new posts." : "Nothing here."}</p>
      ) : (
        <ul className="feed">
          {list.map((c) => (
            <li key={c.id} className={`feed-item ${c.status}`}>
              <div className="feed-head">
                <span className="kind">{CHANGE_KIND[c.kind] || c.kind}</span>
                <span className="muted small">found {fmtDate(c.first_seen_at)}</span>
              </div>
              <b>{c.title}</b>
              <p className="small">{c.what}</p>
              {(c.previous || c.current) && (
                <p className="small"><span className="muted">Before:</span> {c.previous || "–"} <span className="muted">→ Now:</span> {c.current || "–"}</p>
              )}
              <p className="muted small"><b>Why it may matter:</b> {c.why}</p>
              {c.evidence?.length > 0 && (
                <details className="evidence">
                  <summary>Supporting posts ({c.evidence.length})</summary>
                  <div className="post-mini-list">{c.evidence.map((p) => <PostMini key={p.id} p={p} />)}</div>
                </details>
              )}
              <div className="card-actions">
                {c.action?.type === "brief_post" && <BriefButton orgId={orgId} source={{ post_id: c.action.post_id }} onNavigate={onNavigate} label={c.action.label} />}
                {c.action?.type === "brief_topic" && <BriefButton orgId={orgId} source={{ topic: c.action.topic }} onNavigate={onNavigate} label={c.action.label} />}
                {c.action?.type === "explorer" && <button className="btn ghost small-btn" onClick={() => onNavigate("explorer")}>{c.action.label} →</button>}
                {c.status !== "reviewed" && <button className="btn ghost small-btn" onClick={() => mark(c, "reviewed")}>Mark reviewed</button>}
                {c.status !== "saved" && <button className="btn ghost small-btn" onClick={() => mark(c, "saved")}>Save</button>}
                {c.status !== "new" && <button className="link-btn small" onClick={() => mark(c, "new")}>Mark as new</button>}
              </div>
            </li>
          ))}
        </ul>
      )}
      {data && <p className="muted small">{data.note}</p>}
    </section>
  );
}

export default function Suggestions({ orgId, items, readiness, config, onNavigate, refreshKey }) {
  const [kind, setKind] = useState("all");
  const [msg, setMsg] = useState({});
  const [showAll, setShowAll] = useState(false);

  async function track(rec) {
    try {
      await createOpportunity(orgId, rec.key, "save");
      setMsg((m) => ({ ...m, [rec.key]: "Saved to Opportunities." }));
    } catch (e) {
      setMsg((m) => ({ ...m, [rec.key]: e.message }));
    }
  }

  const list = (items || []).filter((r) => kind === "all" || r.kind === kind);
  const counts = Object.fromEntries(KINDS.map((k) => [k.id, (items || []).filter((r) => k.id === "all" || r.kind === k.id).length]));

  return (
    <>
      <ChangeFeed orgId={orgId} refreshKey={refreshKey} onNavigate={onNavigate} />
      <section className="panel">
        <PageHead
          title="Suggestions"
          what={`Built only from the posts, metrics and public comments collected for this workspace${config?.configured ? `, ranked for your ${config.industry_label.toLowerCase()} workspace and goals` : ""}.`}
          why='"What we saw" is measured data; "Why it may matter" is our reading of it, not a verified fact.'
          next="Create a brief from a suggestion, or save it to Opportunities to plan it later."
        />

        <Readiness items={readiness} onNavigate={onNavigate} />

        <div className="chips" role="tablist" aria-label="Filter by kind">
          {KINDS.filter((k) => k.id === "all" || counts[k.id]).map((k) => (
            <button key={k.id} role="tab" aria-selected={kind === k.id} className={`chip ${kind === k.id ? "on" : ""}`} onClick={() => { setKind(k.id); setShowAll(false); }}>
              {k.label} <span className="chip-count">{counts[k.id]}</span>
            </button>
          ))}
        </div>

        {!items ? <Loading /> : list.length === 0 ? (
          <Empty title="No suggestions yet">
            Suggestions appear only when the collected data supports them. Add your account and 2+ competitors, then click Refresh.
          </Empty>
        ) : (
          <div className="sugg-list">
            {(showAll ? list : list.slice(0, FIRST_SHOWN)).map((r) => (
              <RecCard
                key={r.key}
                rec={r}
                actions={
                  r.actionable && (
                    <div className="card-actions">
                      <BriefButton orgId={orgId} source={r.key} onNavigate={onNavigate} />
                      <button className="btn ghost small-btn" onClick={() => track(r)}>Save for later</button>
                      {msg[r.key] && <span className="muted small">{msg[r.key]}</span>}
                    </div>
                  )
                }
              />
            ))}
            {!showAll && list.length > FIRST_SHOWN && (
              <div className="center">
                <button className="btn ghost" onClick={() => setShowAll(true)}>Show all {list.length} suggestions</button>
              </div>
            )}
          </div>
        )}
      </section>
    </>
  );
}
