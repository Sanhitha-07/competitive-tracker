import { useCallback, useEffect, useState } from "react";
import {
  calendarUrl, createOpportunity, evaluateOpportunity, fmtDate, getOpportunities, regenerateBrief,
  sendToMediaOps, STATUS_LABEL, updateOpportunity,
} from "../api";
import { ConfidencePill } from "../components/Evidence";
import Popup from "../components/Popup";
import { Readiness, RecCard } from "./Suggestions";

const MEDIAOPS_PLATFORMS = ["YouTube", "Instagram", "X", "Facebook", "LinkedIn"];
const KIND_LABEL = {
  topic_gap: "Topics", audience_question: "Audience questions", outlier: "Standout posts", format_test: "Formats",
};
const VERDICT = { above_usual: ["good", "Above your usual"], about_usual: ["neutral", "About your usual"], below_usual: ["bad", "Below your usual"] };

function BriefEditor({ orgId, opp, onSaved, onClose }) {
  const [brief, setBrief] = useState(opp.brief || {});
  const [error, setError] = useState("");
  const set = (k) => (e) => setBrief({ ...brief, [k]: e.target.value });

  async function save() {
    try {
      onSaved(await updateOpportunity(orgId, opp.id, { brief }));
      onClose();
    } catch (e) {
      setError(e.message);
    }
  }
  async function regenerate() {
    try {
      const o = await regenerateBrief(orgId, opp.id);
      setBrief(o.brief);
      onSaved(o);
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <Popup title="Content brief" onClose={onClose}>
      <p className="muted small">Built from the evidence. Edit it freely: the references are for research only.</p>
      <label className="field"><span>Working title</span><input value={brief.working_title || ""} onChange={set("working_title")} /></label>
      <label className="field"><span>Angle</span><textarea rows={3} value={brief.angle || ""} onChange={set("angle")} /></label>
      <label className="field"><span>Format</span><input value={brief.format || ""} onChange={set("format")} /></label>
      <div className="meta-grid">
        <div><span>Objective</span><b>{brief.objective}</b></div>
        <div><span>Audience</span><b>{brief.audience}</b></div>
        <div><span>Evidence strength</span><b>{brief.evidence_strength}</b></div>
      </div>
      <div className="field"><span>What we saw</span><p className="plain">{brief.observation}</p></div>
      {brief.questions_to_answer?.length > 0 && (
        <div className="field"><span>Questions to answer</span><ul className="plain">{brief.questions_to_answer.map((q) => <li key={q}>{q}</li>)}</ul></div>
      )}
      {brief.references?.length > 0 && (
        <div className="field">
          <span>References (research only, do not copy)</span>
          <ul className="sources">{brief.references.map((r) => <li key={r.link}><a href={r.link} target="_blank" rel="noreferrer">{r.account}: {r.title}</a></li>)}</ul>
        </div>
      )}
      <div className="field"><span>How we'll measure it</span><p className="plain">{brief.success_measure}</p></div>
      <small className="warn-text">{brief.originality_note}</small>
      {error && <p className="error-text">{error}</p>}
      <div className="popup-actions">
        <button className="btn ghost" onClick={regenerate}>Rebuild from evidence</button>
        <button className="btn primary" onClick={save}>Save brief</button>
      </div>
    </Popup>
  );
}

function MediaOpsDialog({ orgId, opp, apiConfigured, onSaved, onClose }) {
  const [platforms, setPlatforms] = useState(["YouTube"]);
  const [result, setResult] = useState(null);
  const [ref, setRef] = useState(opp.mediaops_ref || "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const toggle = (p) => setPlatforms((cur) => (cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p]));

  async function send() {
    setBusy(true);
    setMsg("");
    try {
      const res = await sendToMediaOps(orgId, opp.id, platforms);
      setResult(res);
      onSaved(res.opportunity);
      if (res.mode === "api") setMsg(`Draft created in MediaOps${res.ref ? ` (${res.ref})` : ""}.`);
    } catch (e) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(result.text);
      setMsg("Copied. In MediaOps open Draft Packages, click Create and paste it.");
    } catch {
      setMsg("Couldn't copy automatically. Select the text and copy it.");
    }
  }
  async function confirm() {
    try {
      onSaved(await updateOpportunity(orgId, opp.id, { status: "in_mediaops", mediaops_ref: ref, note: "Draft created in MediaOps (manual)" }));
      onClose();
    } catch (e) {
      setMsg(e.message);
    }
  }
  return (
    <Popup title="Create in MediaOps" onClose={onClose}>
      <p className="notice small">
        This creates a <b>draft</b> only. Certification, approval, scheduling and publishing stay in MediaOps with your usual permissions.
      </p>
      <div className="field">
        <span>Platforms</span>
        <div className="chips">
          {MEDIAOPS_PLATFORMS.map((p) => (
            <button key={p} type="button" className={`chip ${platforms.includes(p) ? "on" : ""}`} onClick={() => toggle(p)}>{p}</button>
          ))}
        </div>
      </div>
      {!result && (
        <div className="popup-actions">
          <button className="btn primary" onClick={send} disabled={busy || platforms.length === 0}>
            {busy ? "Preparing…" : apiConfigured ? "Create draft in MediaOps" : "Prepare draft"}
          </button>
        </div>
      )}
      {result?.mode === "copy" && (
        <>
          <textarea className="draft-text" readOnly rows={10} value={result.text} />
          <div className="popup-actions"><button className="btn ghost" onClick={copy}>Copy draft</button></div>
          <label className="field">
            <span>Draft Package id or link in MediaOps (optional, keeps the link to results)</span>
            <input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="e.g. DP-1042" />
          </label>
          <div className="popup-actions"><button className="btn primary" onClick={confirm}>I've created the draft</button></div>
        </>
      )}
      {msg && <p className="toast">{msg}</p>}
    </Popup>
  );
}

function DateDialog({ orgId, opp, onSaved, onClose }) {
  const initial = opp.planned_for ? opp.planned_for.slice(0, 16) : "";
  const [when, setWhen] = useState(initial);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(Boolean(opp.planned_for));

  async function save() {
    if (!when) return setError("Pick a date and time.");
    try {
      const status = ["saved", "brief", "in_mediaops"].includes(opp.status) ? "scheduled" : undefined;
      onSaved(await updateOpportunity(orgId, opp.id, { planned_for: new Date(when).toISOString(), ...(status && { status }) }));
      setSaved(true);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <Popup title="Add to calendar" onClose={onClose}>
      <label className="field"><span>Planned for</span><input type="datetime-local" value={when} onChange={(e) => { setWhen(e.target.value); setSaved(false); }} /></label>
      {error && <p className="error-text">{error}</p>}
      <div className="popup-actions">
        <button className="btn primary" onClick={save}>Save date</button>
        {saved && <a className="btn ghost" href={calendarUrl(orgId, opp.id)}>Download calendar file (.ics)</a>}
      </div>
      <p className="muted small">Import the .ics file into Google Calendar or Outlook. In MediaOps, schedule the approved package from Schedules as usual.</p>
    </Popup>
  );
}

function PublishDialog({ orgId, opp, onSaved, onClose }) {
  const [link, setLink] = useState(opp.published_link || "");
  const [error, setError] = useState("");
  async function save() {
    try {
      onSaved(await updateOpportunity(orgId, opp.id, { published_link: link, status: "published", note: "Published" }));
      onClose();
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <Popup title="Mark as published" onClose={onClose}>
      <label className="field">
        <span>Link to the published post</span>
        <input value={link} onChange={(e) => setLink(e.target.value)} placeholder="Link to your published post (YouTube, Instagram, Facebook…)" />
      </label>
      <p className="muted small">After your next Refresh we find this post in your account and measure it 7 days after publishing.</p>
      {error && <p className="error-text">{error}</p>}
      <div className="popup-actions"><button className="btn primary" onClick={save} disabled={!link.trim()}>Save</button></div>
    </Popup>
  );
}

function Outcome({ o }) {
  if (!o) return null;
  if (o.state !== "evaluated") return <span className="muted small">{o.note}</span>;
  const [tone, label] = VERDICT[o.verdict];
  return (
    <div className="outcome">
      <span className={`pill ${tone}`}>{label}</span>
      <span className="small"> {o.views?.toLocaleString("en-IN")} {o.metric || "views"} at 7 days vs your usual {o.baseline_views?.toLocaleString("en-IN")} ({o.ratio}×, baseline from {o.baseline_posts} posts)</span>
      <div className="muted small">{o.note}</div>
    </div>
  );
}

function Pipeline({ orgId, items, onChange, setDialog }) {
  const [msg, setMsg] = useState("");
  const replace = (o) => onChange((list) => list.map((x) => (x.id === o.id ? o : x)));

  async function act(o, status) {
    try {
      replace(await updateOpportunity(orgId, o.id, { status }));
    } catch (e) {
      setMsg(e.message);
    }
  }
  async function measure(o) {
    try {
      const r = await evaluateOpportunity(orgId, o.id);
      setMsg(r.note || "");
      onChange(null); // reload
    } catch (e) {
      setMsg(e.message);
    }
  }

  const active = items.filter((o) => o.status !== "dismissed");
  if (!active.length) return <p className="muted">Nothing saved yet. Use the actions on an opportunity below.</p>;
  return (
    <>
      {msg && <p className="notice small">{msg}</p>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Status</th><th>Opportunity</th><th>Planned</th><th>MediaOps</th><th>Result</th><th></th></tr></thead>
          <tbody>
            {active.map((o) => (
              <tr key={o.id}>
                <td className="nowrap"><span className={`pill status-${o.status}`}>{STATUS_LABEL[o.status]}</span></td>
                <td className="story">
                  {o.title}
                  <div className="muted small">{KIND_LABEL[o.kind] || o.kind} · saved {fmtDate(o.created_at)} <ConfidencePill confidence={o.snapshot?.confidence} /></div>
                </td>
                <td className="nowrap small">{o.planned_for ? fmtDate(o.planned_for) : "–"}</td>
                <td className="small">{o.mediaops_ref || "–"}</td>
                <td className="small">
                  {o.published_link && <a href={o.published_link} target="_blank" rel="noreferrer">Published post</a>}
                  <Outcome o={o.outcome} />
                </td>
                <td>
                  <div className="row-actions">
                    {o.status !== "evaluated" && o.status !== "published" && (
                      <>
                        <button className="btn ghost small-btn" onClick={() => setDialog({ mode: "brief", opp: o })}>{o.brief ? "Brief" : "Generate brief"}</button>
                        <button className="btn ghost small-btn" onClick={() => setDialog({ mode: "mediaops", opp: o })}>Create in MediaOps</button>
                        <button className="btn ghost small-btn" onClick={() => setDialog({ mode: "date", opp: o })}>Calendar</button>
                        <button className="btn ghost small-btn" onClick={() => setDialog({ mode: "publish", opp: o })}>Mark published</button>
                        <button className="btn ghost small-btn" onClick={() => act(o, "dismissed")}>Dismiss</button>
                      </>
                    )}
                    {(o.status === "published" || o.status === "evaluated") && (
                      <button className="btn ghost small-btn" onClick={() => measure(o)}>{o.status === "evaluated" ? "Re-check" : "Measure now"}</button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Dialogs({ orgId, dialog, setDialog, apiConfigured, replace }) {
  if (!dialog) return null;
  const close = () => setDialog(null);
  const { mode, opp } = dialog;
  if (mode === "brief") {
    return opp.brief
      ? <BriefEditor orgId={orgId} opp={opp} onSaved={replace} onClose={close} />
      : <BriefLoader orgId={orgId} opp={opp} onSaved={(o) => { replace(o); setDialog({ mode: "brief", opp: o }); }} onClose={close} />;
  }
  if (mode === "mediaops") return <MediaOpsDialog orgId={orgId} opp={opp} apiConfigured={apiConfigured} onSaved={replace} onClose={close} />;
  if (mode === "date") return <DateDialog orgId={orgId} opp={opp} onSaved={replace} onClose={close} />;
  if (mode === "publish") return <PublishDialog orgId={orgId} opp={opp} onSaved={replace} onClose={close} />;
  return null;
}

function BriefLoader({ orgId, opp, onSaved, onClose }) {
  const [error, setError] = useState("");
  useEffect(() => {
    regenerateBrief(orgId, opp.id).then(onSaved).catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <Popup title="Content brief" onClose={onClose}>{error ? <p className="error-text">{error}</p> : <p className="muted">Building brief…</p>}</Popup>;
}

function Learned({ stats }) {
  const rows = Object.entries(stats || {}).filter(([, s]) => s.accepted || s.dismissed);
  if (!rows.length) return null;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Kind</th><th>Accepted</th><th>Published</th><th>Measured</th><th>Above your usual</th><th>Dismissed</th></tr></thead>
        <tbody>
          {rows.map(([k, s]) => (
            <tr key={k}>
              <td>{KIND_LABEL[k] || k}</td><td className="num">{s.accepted}</td><td className="num">{s.implemented}</td>
              <td className="num">{s.evaluated}</td><td className="num">{s.evaluated ? `${s.above} of ${s.evaluated}` : "–"}</td><td className="num">{s.dismissed}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">After 3+ measured results, a kind that tends to beat your usual results is ranked a little higher. This is an association, not proof of cause.</p>
    </div>
  );
}

export default function Opportunities({ orgId, onNavigate, refreshKey }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState({});
  const [dialog, setDialog] = useState(null); // {mode: "brief" | "mediaops" | "date" | "publish", opp}

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await getOpportunities(orgId));
      setError("");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  function setTracked(updater) {
    if (updater === null) return load();
    setData((d) => ({ ...d, tracked: updater(d.tracked) }));
  }

  const replace = (o) => setTracked((list) => list.map((x) => (x.id === o.id ? o : x)));

  // Save the opportunity (with its evidence), then open the dialog for the chosen action.
  async function start(rec, action, mode) {
    try {
      const o = await createOpportunity(orgId, rec.key, action);
      setData((d) => ({ ...d, suggested: d.suggested.filter((r) => r.key !== rec.key), tracked: [o, ...d.tracked.filter((t) => t.id !== o.id)] }));
      setMsg((m) => ({ ...m, pipeline: mode ? "" : "Saved for later. It's in your pipeline above." }));
      if (mode) setDialog({ mode, opp: o });
    } catch (e) {
      setMsg((m) => ({ ...m, [rec.key]: e.message }));
    }
  }

  if (error) return <section className="panel"><div className="empty"><b>Opportunities not available</b><span>{error}</span></div></section>;
  if (!data) return <section className="panel"><div className="empty"><b>Loading opportunities…</b></div></section>;

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Your opportunity pipeline</h2>
            <p className="muted">Each one keeps its original evidence, so you can follow it from idea → brief → MediaOps draft → published post → result.</p>
          </div>
          {loading && <span className="muted small">Updating…</span>}
        </div>
        {msg.pipeline && <p className="toast">{msg.pipeline}</p>}
        <Pipeline orgId={orgId} items={data.tracked} onChange={setTracked} setDialog={setDialog} />
        <Learned stats={data.learned} />
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>New opportunities</h2>
            <p className="muted">Competitive observations turned into content ideas. Nothing is shown without data behind it.</p>
          </div>
        </div>
        <Readiness items={data.readiness} onNavigate={onNavigate} />
        {data.suggested.length === 0 ? (
          <div className="empty"><b>No new opportunities</b><span>Add competitors, click Refresh, or check back after they publish more.</span></div>
        ) : (
          <div className="sugg-list">
            {data.suggested.map((r) => (
              <RecCard
                key={r.key}
                rec={r}
                actions={
                  <div className="card-actions">
                    <button className="btn primary small-btn" onClick={() => start(r, "brief", "brief")}>Generate brief</button>
                    <button className="btn ghost small-btn" onClick={() => start(r, "brief", "mediaops")}>Create in MediaOps</button>
                    <button className="btn ghost small-btn" onClick={() => start(r, "save", "date")}>Add to calendar</button>
                    <button className="btn ghost small-btn" onClick={() => start(r, "save")}>Save for later</button>
                    {msg[r.key] && <span className="error-text">{msg[r.key]}</span>}
                  </div>
                }
              />
            ))}
          </div>
        )}
      </section>
      <Dialogs orgId={orgId} dialog={dialog} setDialog={setDialog} apiConfigured={data.mediaops_api} replace={replace} />
    </>
  );
}
