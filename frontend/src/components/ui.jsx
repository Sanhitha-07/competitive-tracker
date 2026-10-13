import { useId, useState } from "react";
import { createOpportunity } from "../api";

// Page header that answers: what am I looking at, why does it matter, what can I do next.
export function PageHead({ title, what, why, next, children }) {
  return (
    <div className="panel-head">
      <div className="page-intro">
        <h2>{title}</h2>
        {what && <p className="muted">{what}</p>}
        {(why || next) && (
          <p className="intro-lines small">
            {why && <span><b>Why it matters:</b> {why}</span>}
            {next && <span><b>Next:</b> {next}</span>}
          </p>
        )}
      </div>
      {children && <div className="head-tools">{children}</div>}
    </div>
  );
}

// A small "i" that explains a metric on hover or keyboard focus.
export function Tip({ text, label = "What does this mean?" }) {
  const id = useId();
  if (!text) return null;
  return (
    <span className="tip" tabIndex={0} aria-label={label} aria-describedby={id}>
      i<span className="tip-text" role="tooltip" id={id}>{text}</span>
    </span>
  );
}

export function Empty({ title, children }) {
  return <div className="empty"><b>{title}</b>{children && <span>{children}</span>}</div>;
}

export function Loading({ what = "Loading…" }) {
  return <div className="empty" aria-busy="true"><span className="spinner" aria-hidden="true" /><span>{what}</span></div>;
}

// "Create brief" from a topic, a post or a recommendation key. Opens nothing by itself:
// the brief is saved to Opportunities, and nothing is ever published.
export function BriefButton({ orgId, source, onNavigate, label = "Create brief", className = "btn primary small-btn" }) {
  const [state, setState] = useState("");
  const [error, setError] = useState("");
  async function go() {
    setState("busy");
    setError("");
    try {
      await createOpportunity(orgId, source, "brief");
      setState("done");
    } catch (e) {
      setError(e.message);
      setState("");
    }
  }
  if (state === "done") {
    return (
      <button className="btn ghost small-btn" onClick={() => onNavigate?.("opportunities")} title="The brief is saved in Opportunities">
        Brief ready →
      </button>
    );
  }
  return (
    <>
      <button className={className} onClick={go} disabled={state === "busy"}>{state === "busy" ? "Creating…" : label}</button>
      {error && <span className="error-text small" role="alert">{error}</span>}
    </>
  );
}

export function Pill({ tone = "neutral", children, title }) {
  return <span className={`pill ${tone}`} title={title}>{children}</span>;
}
