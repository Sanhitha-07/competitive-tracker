import { useState } from "react";
import { createOpportunity } from "../api";
import Evidence, { ConfidencePill } from "../components/Evidence";

const KINDS = [
  { id: "all", label: "All" },
  { id: "topic_gap", label: "Topics" },
  { id: "audience_question", label: "Audience questions" },
  { id: "outlier", label: "Standout competitor posts" },
  { id: "format_test", label: "Formats to test" },
  { id: "publishing_pattern", label: "Publishing patterns" },
  { id: "benchmark", label: "Benchmarks" },
];

export function Readiness({ items, onNavigate }) {
  if (!items?.length) return null;
  return (
    <div className="readiness">
      <b>To get better recommendations:</b>
      <ul>{items.map((n) => <li key={n}>{n}</li>)}</ul>
      <div className="chips">
        <button className="btn ghost small-btn" onClick={() => onNavigate("workspace")}>Workspace settings</button>
        <button className="btn ghost small-btn" onClick={() => onNavigate("accounts")}>Accounts</button>
      </div>
    </div>
  );
}

export function RecCard({ rec, actions }) {
  return (
    <article className={`sugg ${rec.tone}`}>
      <div className="sugg-head">
        <span className="kind">{rec.kind_label}</span>
        <ConfidencePill confidence={rec.confidence} />
      </div>
      <b>{rec.title}</b>
      <p><span className="lbl">Observed:</span> {rec.observed}</p>
      <p><span className="lbl">Why it's relevant to you:</span> {rec.why_relevant}</p>
      {rec.suggested_format_label && <p><span className="lbl">Suggested format:</span> {rec.suggested_format_label}</p>}
      <p><span className="lbl">Next step:</span> {rec.next_step}</p>
      <Evidence rec={rec} />
      {actions}
    </article>
  );
}

export default function Suggestions({ orgId, items, readiness, config, onNavigate, onTracked }) {
  const [kind, setKind] = useState("all");
  const [msg, setMsg] = useState({});

  async function track(rec) {
    try {
      await createOpportunity(orgId, rec.key, "save");
      setMsg((m) => ({ ...m, [rec.key]: "Saved to Opportunities." }));
      onTracked?.();
    } catch (e) {
      setMsg((m) => ({ ...m, [rec.key]: e.message }));
    }
  }

  const list = (items || []).filter((r) => kind === "all" || r.kind === kind);
  const counts = Object.fromEntries(KINDS.map((k) => [k.id, (items || []).filter((r) => k.id === "all" || r.kind === k.id).length]));

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Suggestions</h2>
          <p className="muted">
            Built only from the posts, metrics and public comments collected for this workspace
            {config?.configured ? `, ranked for your ${config.industry_label.toLowerCase()} workspace and goals.` : "."}
            {" "}Open "Evidence" on any card to see the sample, data period and limitations.
          </p>
        </div>
      </div>

      <Readiness items={readiness} onNavigate={onNavigate} />

      <div className="chips" role="tablist" aria-label="Filter by kind">
        {KINDS.filter((k) => k.id === "all" || counts[k.id]).map((k) => (
          <button key={k.id} className={`chip ${kind === k.id ? "on" : ""}`} onClick={() => setKind(k.id)}>
            {k.label} <span className="chip-count">{counts[k.id]}</span>
          </button>
        ))}
      </div>

      {list.length === 0 ? (
        <div className="empty">
          <b>No suggestions yet</b>
          <span>Suggestions appear only when the collected data supports them. Add your account and 2+ competitors, then click Refresh.</span>
        </div>
      ) : (
        <div className="sugg-list">
          {list.map((r) => (
            <RecCard
              key={r.key}
              rec={r}
              actions={
                r.actionable && (
                  <div className="card-actions">
                    <button className="btn ghost small-btn" onClick={() => track(r)}>Save as opportunity</button>
                    {msg[r.key] && <span className="muted small">{msg[r.key]}</span>}
                  </div>
                )
              }
            />
          ))}
        </div>
      )}
    </section>
  );
}
