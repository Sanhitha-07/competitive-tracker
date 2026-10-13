import { useCallback, useEffect, useState } from "react";
import {
  createExperiment, deleteExperiment, evaluateExperiment, fmtDate, getExperiments, STATUS_LABEL, updateExperiment,
} from "../api";
import { PostMini } from "../components/Evidence";
import Popup from "../components/Popup";
import { Empty, Loading, PageHead } from "../components/ui";

const STATUS_TONE = { planned: "neutral", running: "warn", completed: "good", cancelled: "neutral" };
const RESULT = { successful: ["good", "Successful"], unsuccessful: ["bad", "Unsuccessful"], inconclusive: ["warn", "Inconclusive"] };
const EFFORT_TONE = { low: "good", medium: "warn", high: "bad" };

function experimentFromStrategy(s) {
  return {
    hypothesis: s.hypothesis, reason: s.why, evidence: { strategy: s.id, observations: s.observations, sample: s.sample },
    variable_type: s.variable_type, variable_value: s.variable_value, target_metric: s.metric,
    success_threshold: s.threshold ?? "", duration_days: s.duration.weeks * 7, min_posts: s.duration.posts,
  };
}

function goalText(e, metrics) {
  const m = metrics.find((x) => x.id === e.target_metric);
  const unit = m?.unit === "×" ? "×" : m?.unit === "%" ? "%" : "";
  return `median ${m?.label.toLowerCase() || e.target_metric} ≥ ${e.success_threshold}${unit}`;
}

function ExperimentForm({ initial, metrics, opportunities, onSave, onClose }) {
  const [f, setF] = useState({
    hypothesis: "", reason: "", variable_type: "other", variable_value: "", target_metric: "views_vs_usual",
    success_threshold: 1.2, min_posts: 3, duration_days: 28, opportunity_id: "", evidence: {}, ...initial,
  });
  const [error, setError] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const metric = metrics.find((m) => m.id === f.target_metric);

  async function save() {
    if (f.hypothesis.trim().length < 5) return setError("Write the hypothesis you want to test.");
    const threshold = Number(f.success_threshold);
    if (!threshold || threshold <= 0) return setError("Set the goal as a number above 0.");
    try {
      await onSave({
        ...f, success_threshold: threshold, min_posts: Number(f.min_posts), duration_days: Number(f.duration_days),
        opportunity_id: f.opportunity_id ? Number(f.opportunity_id) : null, variable_value: f.variable_value || null,
      });
      onClose();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <Popup title="New experiment" onClose={onClose}>
      <label className="field"><span>Hypothesis</span>
        <textarea rows={2} value={f.hypothesis} onChange={set("hypothesis")} placeholder="e.g. Beginner tutorial videos will perform better for our audience than our usual videos." />
      </label>
      <label className="field"><span>Why test it?</span><textarea rows={2} value={f.reason || ""} onChange={set("reason")} /></label>
      <div className="form-row">
        <label className="field"><span>What changes</span>
          <select value={f.variable_type} onChange={set("variable_type")}>
            <option value="format">A format</option><option value="topic">A topic or angle</option><option value="other">Something else</option>
          </select>
        </label>
        <label className="field grow"><span>Which one</span><input value={f.variable_value || ""} onChange={set("variable_value")} placeholder="e.g. short, how-to, protein" /></label>
      </div>
      <div className="form-row">
        <label className="field grow"><span>Measure with</span>
          <select value={f.target_metric} onChange={set("target_metric")}>
            {metrics.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
          <small className="muted">{metric?.definition}</small>
        </label>
        <label className="field"><span>Success if the median is at least</span>
          <input type="number" step="any" min="0" value={f.success_threshold} onChange={set("success_threshold")} />
        </label>
      </div>
      <div className="form-row">
        <label className="field"><span>Posts needed</span><input type="number" min="1" max="50" value={f.min_posts} onChange={set("min_posts")} /></label>
        <label className="field"><span>Length (days)</span><input type="number" min="7" max="180" value={f.duration_days} onChange={set("duration_days")} /></label>
        <label className="field grow"><span>Brief / MediaOps draft</span>
          <select value={f.opportunity_id || ""} onChange={set("opportunity_id")}>
            <option value="">None yet</option>
            {opportunities.map((o) => <option key={o.id} value={o.id}>{o.title.slice(0, 70)} ({STATUS_LABEL[o.status]})</option>)}
          </select>
        </label>
      </div>
      <p className="muted small">The goal is set before you see results, so the result can't be judged after the fact. Fewer posts than needed = "inconclusive".</p>
      {error && <p className="error-text">{error}</p>}
      <div className="popup-actions">
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" onClick={save}>Create experiment</button>
      </div>
    </Popup>
  );
}

function Result({ r, metrics }) {
  if (!r) return null;
  const [tone, label] = RESULT[r.state];
  const unit = metrics.find((m) => m.id === r.metric)?.unit;
  return (
    <div className="result-box">
      <div className="row-between">
        <span className={`pill ${tone}`}>{label}</span>
        <span className="muted small">measured {fmtDate(r.evaluated_at)}</span>
      </div>
      <p className="small">
        Median result <b>{r.median ?? "–"}{unit === "×" ? "×" : unit === "%" ? "%" : ""}</b> vs goal {r.threshold} · {r.measured_posts} of {r.min_posts} posts measured
        {r.median_vs_usual !== null && r.metric !== "views_vs_usual" && <> · {r.median_vs_usual}× your usual views</>}
      </p>
      <p className="muted small">{r.note}</p>
      {r.posts.length > 0 && (
        <div className="table-wrap">
          <table className="compact-table">
            <thead><tr><th>Post</th><th>Source</th><th className="num">Result</th><th>Note</th></tr></thead>
            <tbody>
              {r.posts.map((p, i) => (
                <tr key={i}>
                  <td className="small">{p.link ? <a href={p.link} target="_blank" rel="noreferrer">{p.title || p.link}</a> : "–"}</td>
                  <td className="small">{p.source === "manual" ? "Entered by you" : "Tracker"}</td>
                  <td className="num">{p.value ?? "–"}</td>
                  <td className="muted small">{p.note || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ExperimentCard({ orgId, e, metrics, onChange, onDelete, onNavigate }) {
  const [link, setLink] = useState("");
  const [manual, setManual] = useState({ value: "", link: "", note: "" });
  const [learning, setLearning] = useState(e.learning || "");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function patch(data, done) {
    setBusy(true);
    setMsg("");
    try {
      onChange(await updateExperiment(orgId, e.id, data));
      done?.();
    } catch (err) {
      setMsg(err.message);
    } finally {
      setBusy(false);
    }
  }
  async function measure() {
    setBusy(true);
    setMsg("");
    try {
      onChange(await evaluateExperiment(orgId, e.id));
    } catch (err) {
      setMsg(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="exp-card">
      <div className="sugg-head">
        <span className={`pill ${STATUS_TONE[e.status]}`}>{e.status[0].toUpperCase() + e.status.slice(1)}</span>
        <span className="muted small">
          {e.started_at ? `Started ${fmtDate(e.started_at)} · ends ${fmtDate(e.ends_at)}` : `Planned · ${e.duration_days} days once started`}
        </span>
      </div>
      <b className="sugg-title">{e.hypothesis}</b>
      {e.reason && <p className="small"><span className="lbl">Why:</span> {e.reason}</p>}
      <p className="meta-line small">
        <span>Goal: {goalText(e, metrics)}</span>
        <span>Needs {e.min_posts} posts</span>
        {e.variable_value && <span>Testing: {e.variable_value}</span>}
        {e.opportunity && <span>Brief: <button className="link-btn" onClick={() => onNavigate("opportunities")}>{e.opportunity.title.slice(0, 50)}</button> ({STATUS_LABEL[e.opportunity.status]})</span>}
      </p>
      {e.evidence?.observations?.length > 0 && (
        <details className="evidence"><summary>Evidence when it was created</summary><ul className="limits">{e.evidence.observations.map((o) => <li key={o}>{o}</li>)}</ul></details>
      )}

      <div className="field">
        <span>Posts made for this experiment</span>
        {e.post_links.length > 0 ? (
          <ul className="sources">
            {e.post_links.map((l) => (
              <li key={l}><a href={l} target="_blank" rel="noreferrer">{l}</a> <button className="link-btn small" onClick={() => patch({ remove_post_link: l })}>remove</button></li>
            ))}
          </ul>
        ) : <p className="muted small">None yet. Add each published post's link; results are measured 7 days after publishing.</p>}
        <form className="inline-form" onSubmit={(ev) => { ev.preventDefault(); if (link.trim()) patch({ add_post_link: link }, () => setLink("")); }}>
          <input value={link} onChange={(ev) => setLink(ev.target.value)} placeholder="https://www.youtube.com/watch?v=…" aria-label="Published post link" />
          <button className="btn ghost small-btn" type="submit" disabled={busy}>Add post</button>
        </form>
      </div>

      <details className="evidence" open={e.target_metric === "manual"}>
        <summary>Record a result by hand {e.manual_results.length > 0 && `(${e.manual_results.length})`}</summary>
        <p className="muted small">For numbers the tracker can't read (e.g. website page views, sign-ups). They're labelled "Entered by you".</p>
        {e.manual_results.length > 0 && (
          <ul className="limits">
            {e.manual_results.map((m, i) => (
              <li key={i}>{m.value}{m.link && <> · <a href={m.link} target="_blank" rel="noreferrer">post</a></>}{m.note && ` · ${m.note}`}{" "}
                <button className="link-btn small" onClick={() => patch({ remove_manual_result: i })}>remove</button></li>
            ))}
          </ul>
        )}
        <form className="inline-form" onSubmit={(ev) => { ev.preventDefault(); patch({ add_manual_result: manual }, () => setManual({ value: "", link: "", note: "" })); }}>
          <input type="number" step="any" value={manual.value} onChange={(ev) => setManual({ ...manual, value: ev.target.value })} placeholder="Value" aria-label="Result value" required />
          <input value={manual.link} onChange={(ev) => setManual({ ...manual, link: ev.target.value })} placeholder="Post link (optional)" aria-label="Post link" />
          <input value={manual.note} onChange={(ev) => setManual({ ...manual, note: ev.target.value })} placeholder="Note (optional)" aria-label="Note" />
          <button className="btn ghost small-btn" type="submit" disabled={busy}>Record</button>
        </form>
      </details>

      <Result r={e.result} metrics={metrics} />

      {(e.result || e.status === "completed") && (
        <label className="field">
          <span>What we learned</span>
          <textarea rows={2} value={learning} onChange={(ev) => setLearning(ev.target.value)} placeholder="e.g. Tutorials beat our usual on 3 of 4 posts; keep testing with different topics." />
          {learning !== (e.learning || "") && <div><button className="btn ghost small-btn" onClick={() => patch({ learning })}>Save learning</button></div>}
        </label>
      )}

      {msg && <p className="error-text small">{msg}</p>}
      <div className="card-actions">
        {(e.post_links.length > 0 || e.manual_results.length > 0) && <button className="btn primary small-btn" onClick={measure} disabled={busy}>Measure results</button>}
        {e.status === "planned" && <button className="btn ghost small-btn" onClick={() => patch({ status: "running" })}>Start</button>}
        {e.status === "running" && <button className="btn ghost small-btn" onClick={() => patch({ status: "completed" })}>Mark completed</button>}
        {e.status === "completed" && <button className="btn ghost small-btn" onClick={() => patch({ status: "running" })}>Reopen</button>}
        {["planned", "running"].includes(e.status) && <button className="btn ghost small-btn" onClick={() => patch({ status: "cancelled" })}>Cancel</button>}
        {e.status === "cancelled" && <button className="btn ghost small-btn" onClick={() => patch({ status: "planned" })}>Restore</button>}
        <button className="link-btn small danger-link" onClick={() => onDelete(e)}>Delete</button>
      </div>
    </article>
  );
}

function Strategy({ s, onStart }) {
  return (
    <article className="sugg info">
      <div className="sugg-head">
        <span className="kind">Strategy to test</span>
        <span className={`pill ${EFFORT_TONE[s.effort.level]}`} title={s.effort.reason}>{s.effort.level} effort</span>
      </div>
      <b className="sugg-title">{s.title}</b>
      <p><span className="lbl">Why it may be worth testing:</span> {s.why}</p>
      <ul className="limits">{s.observations.map((o) => <li key={o}>{o}</li>)}</ul>
      <p className="meta-line small">
        <span>Sample: {s.sample}</span>
        <span>Suggested test: {s.duration.posts} posts over ~{s.duration.weeks} weeks</span>
        <span>Measure: {s.metric_label}</span>
      </p>
      <details className="evidence">
        <summary>Limitations and supporting posts</summary>
        <ul className="limits">{s.limitations.map((l) => <li key={l}>{l}</li>)}<li>{s.duration.reason}</li></ul>
        {s.evidence?.length > 0 && <div className="post-mini-list">{s.evidence.map((p) => <PostMini key={p.id} p={p} />)}</div>}
      </details>
      <div className="card-actions"><button className="btn primary small-btn" onClick={() => onStart(s)}>Start an experiment</button></div>
    </article>
  );
}

export default function Experiments({ orgId, refreshKey, prefill, onPrefillUsed, onNavigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const load = useCallback(async () => {
    try {
      setData(await getExperiments(orgId));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, [orgId]);

  useEffect(() => { load(); }, [load, refreshKey]);
  useEffect(() => {
    if (prefill) {
      setForm(prefill);
      onPrefillUsed?.();
    }
  }, [prefill, onPrefillUsed]);

  const replace = (e) => setData((d) => ({ ...d, experiments: d.experiments.map((x) => (x.id === e.id ? { ...x, ...e } : x)) }));

  if (error) return <section className="panel"><Empty title="Experiments not available">{error}</Empty></section>;
  if (!data) return <section className="panel"><Loading what="Loading experiments…" /></section>;
  const sim = data.simulator;

  return (
    <>
      <section className="panel">
        <PageHead
          title="Strategies worth testing"
          what="Ideas built from patterns in your collected data. Each is a hypothesis to test, not a prediction: no views or revenue are forecast."
          next="Start an experiment to test one with a few posts, measured against your own usual results."
        />
        {sim.strategies.length === 0 ? (
          <Empty title="No strategy stands out yet">{sim.why_none.join(" ")}</Empty>
        ) : (
          <div className="sugg-list">{sim.strategies.map((s) => <Strategy key={s.id} s={s} onStart={(x) => setForm(experimentFromStrategy(x))} />)}</div>
        )}
      </section>

      <section className="panel">
        <PageHead
          title="Your experiments"
          what="Each experiment has a goal set in advance. Results are measured 7 days after each post, against your goal and your usual views."
        >
          <button className="btn primary small-btn" onClick={() => setForm({})}>+ New experiment</button>
        </PageHead>
        {data.experiments.length === 0 ? (
          <Empty title="No experiments yet">Start one from a strategy above, or from an opportunity ("Test as experiment").</Empty>
        ) : (
          <div className="sugg-list">
            {data.experiments.map((e) => (
              <ExperimentCard key={e.id} orgId={orgId} e={e} metrics={data.metrics} onChange={replace} onDelete={setConfirm} onNavigate={onNavigate} />
            ))}
          </div>
        )}
        <p className="muted small">One successful experiment is a good sign, not proof that a strategy will always work. Repeat what works with new topics.</p>
      </section>

      {form && (
        <ExperimentForm initial={form} metrics={data.metrics} opportunities={data.opportunities}
          onSave={async (body) => { await createExperiment(orgId, body); await load(); }} onClose={() => setForm(null)} />
      )}
      {confirm && (
        <Popup title="Delete experiment?" onClose={() => setConfirm(null)}>
          <p>Delete "{confirm.hypothesis}" and its recorded results? This can't be undone.</p>
          <div className="popup-actions">
            <button className="btn ghost" onClick={() => setConfirm(null)}>Cancel</button>
            <button className="btn danger" onClick={async () => { await deleteExperiment(orgId, confirm.id); setConfirm(null); load(); }}>Delete</button>
          </div>
        </Popup>
      )}
    </>
  );
}
