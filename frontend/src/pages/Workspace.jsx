import { useEffect, useMemo, useState } from "react";
import { PLATFORM_LABEL, saveConfig } from "../api";
import { PageHead } from "../components/ui";

const WINDOWS = [
  [24, "Last 24 hours"], [72, "Last 3 days"], [168, "Last 7 days"], [336, "Last 14 days"],
  [720, "Last 30 days"], [1440, "Last 60 days"], [2160, "Last 90 days"],
];
const ZONES = ["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "Europe/Berlin",
  "America/New_York", "America/Chicago", "America/Los_Angeles", "Australia/Sydney", "UTC"];

function fromConfig(cfg, org) {
  return {
    name: org?.name || "",
    creator_type: cfg?.creator_type || "",
    category: cfg?.industry || "other",
    niche: cfg?.niche || "",
    sub_niche: cfg?.sub_niche || "",
    audience: cfg?.audience || "",
    goals: cfg?.goals || [],
    topicsText: (cfg?.topics || []).join(", "),
    formats: cfg?.formats || [],
    platforms: cfg?.platforms || [],
    timezone: cfg?.timezone || "Asia/Kolkata",
    time_sensitive: Boolean(cfg?.time_sensitive),
    window_hours: org?.window_hours || cfg?.window_hours || 720,
  };
}

export default function Workspace({ orgId, org, config, options, onSaved, onNavigate }) {
  const [form, setForm] = useState(() => fromConfig(config, org));
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setForm(fromConfig(config, org));
    setSaved("");
    setError("");
  }, [config, org]);

  const topics = useMemo(
    () => form.topicsText.split(/[,\n]/).map((t) => t.trim()).filter(Boolean),
    [form.topicsText]
  );
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const toggle = (k, v) => setForm((f) => ({ ...f, [k]: f[k].includes(v) ? f[k].filter((x) => x !== v) : [...f[k], v] }));

  function pickIndustry(e) {
    const id = e.target.value;
    const ind = options?.industries.find((i) => i.id === id);
    // Industry gives sensible starting values; the user can change them.
    setForm((f) => ({ ...f, category: id, window_hours: ind?.window_hours ?? f.window_hours, time_sensitive: ind?.time_sensitive ?? f.time_sensitive }));
  }

  async function onSubmit(e) {
    e.preventDefault();
    if (!form.name.trim()) return setError("Enter a workspace or brand name.");
    if (!form.creator_type) return setError("Choose what kind of creator or business this workspace is for.");
    if (form.category === "other" && !form.niche.trim()) return setError('With industry "Other", describe your niche.');
    if (topics.some((t) => t.length > 60)) return setError("Each topic or keyword can be up to 60 characters.");
    setSaving(true);
    try {
      const { topicsText: _unused, ...rest } = form;
      const res = await saveConfig(orgId, { ...rest, topics, window_hours: Number(form.window_hours) });
      setError("");
      setSaved("Saved. Suggestions and coverage gaps now use these settings.");
      onSaved(res.organization, res.config);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (!options) return <section className="panel"><div className="empty"><b>Loading settings…</b></div></section>;
  const supported = options.platforms.supported;
  const planned = options.platforms.planned;

  return (
    <section className="panel">
      <PageHead
        title="Workspace settings"
        what="Who this workspace is for and what you care about. You can change these at any time."
        why="Your niche, topics and goals decide which competitor topics count as relevant and how suggestions are prioritised. They never invent data."
        next="Save, then add your accounts and competitors in Accounts."
      />

      <form className="ws-form" onSubmit={onSubmit} noValidate>
        <fieldset>
          <legend>Who is this for?</legend>
          <label className="field">
            <span>Workspace or brand name</span>
            <input id="ws-name" value={form.name} onChange={set("name")} maxLength={80} />
          </label>
          <label className="field">
            <span>Creator / business type</span>
            <select id="ws-type" value={form.creator_type} onChange={set("creator_type")}>
              <option value="">Choose…</option>
              {options.creator_types.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Industry</span>
            <select id="ws-industry" value={form.category} onChange={pickIndustry}>
              {options.industries.map((i) => <option key={i.id} value={i.id}>{i.label}</option>)}
            </select>
          </label>
          <label className="field grow">
            <span>Niche {form.category === "other" ? "(required)" : "(optional)"}</span>
            <input id="ws-niche" value={form.niche} onChange={set("niche")} maxLength={120} placeholder="e.g. home strength training, indie horror games, Python for data analysts" />
          </label>
          <label className="field grow">
            <span>Sub-niche (optional)</span>
            <input id="ws-subniche" value={form.sub_niche} onChange={set("sub_niche")} maxLength={120} placeholder="e.g. kettlebells for beginners, B2B invoicing software" />
          </label>
          <label className="field full">
            <span>Target audience</span>
            <input id="ws-audience" value={form.audience} onChange={set("audience")} maxLength={300} placeholder="e.g. busy parents in their 30s, beginner programmers, small business owners" />
          </label>
        </fieldset>

        <fieldset>
          <legend>Content goals</legend>
          <div className="chips">
            {options.goals.map((g) => (
              <button type="button" key={g.id} className={`chip ${form.goals.includes(g.id) ? "on" : ""}`} onClick={() => toggle("goals", g.id)} aria-pressed={form.goals.includes(g.id)}>
                {g.label}
              </button>
            ))}
          </div>
          <small className="muted">Goals change the order of recommendations (e.g. "Answer my audience's questions" puts audience questions first).</small>
        </fieldset>

        <fieldset>
          <legend>Topics and keywords to track</legend>
          <label className="field full">
            <span>Separate with commas</span>
            <textarea id="ws-topics" rows={2} value={form.topicsText} onChange={set("topicsText")} placeholder="e.g. protein, kettlebell, mobility, meal prep" />
          </label>
          {topics.length > 0 && <div className="chips">{topics.map((t) => <span className="chip static" key={t}>{t}</span>)}</div>}
          <small className="muted">These always appear in the Coverage Gaps map, even when no one has posted about them yet.
            {config?.topic_rules && (Object.keys(config.topic_rules.aliases).length + config.topic_rules.excluded.length) > 0 &&
              ` You've also made ${Object.keys(config.topic_rules.aliases).length + config.topic_rules.excluded.length} topic correction(s); manage them in Coverage Gaps.`}</small>
        </fieldset>

        <fieldset>
          <legend>Preferred content formats</legend>
          <div className="chips">
            {options.formats.map((f) => (
              <button type="button" key={f.id} className={`chip ${form.formats.includes(f.id) ? "on" : ""}`} onClick={() => toggle("formats", f.id)} aria-pressed={form.formats.includes(f.id)}
                title={f.detectable ? "" : "We can't detect this format in the collected data yet"}>
                {f.label}{!f.detectable && " *"}
              </button>
            ))}
          </div>
          <small className="muted">* Not detectable in the data from the platforms connected so far.</small>
        </fieldset>

        <fieldset>
          <legend>Platforms</legend>
          <div className="chips">
            {supported.map((p) => (
              <button type="button" key={p.id} className={`chip ${form.platforms.includes(p.id) ? "on" : ""}`} onClick={() => toggle("platforms", p.id)} aria-pressed={form.platforms.includes(p.id)}>
                {PLATFORM_LABEL[p.id] || p.label}
              </button>
            ))}
            {planned.map((p) => (
              <span key={p.id} className="chip disabled" title={p.reason}>{p.label} (not yet)</span>
            ))}
          </div>
          <small className="muted">Hover over a "not yet" platform to see what's needed to connect it.</small>
        </fieldset>

        <fieldset>
          <legend>Comparison</legend>
          <label className="field">
            <span>Compare posts from</span>
            <select id="ws-window" value={form.window_hours} onChange={set("window_hours")}>
              {WINDOWS.map(([h, l]) => <option key={h} value={h}>{l}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Time zone (for posting times)</span>
            <input id="ws-tz" list="tz-list" value={form.timezone} onChange={set("timezone")} />
            <datalist id="tz-list">{ZONES.map((z) => <option key={z} value={z} />)}</datalist>
          </label>
          <label className="check">
            <input id="ws-sensitive" type="checkbox" checked={form.time_sensitive} onChange={set("time_sensitive")} />
            Time-sensitive content (show "First to Publish")
          </label>
        </fieldset>

        <fieldset>
          <legend>Connected accounts and competitors</legend>
          <p className="muted">Your own accounts and the competitors you compare against are managed in Accounts.</p>
          <button type="button" className="btn ghost small-btn" onClick={() => onNavigate("accounts")}>Go to Accounts</button>
        </fieldset>

        {error && <p className="error-text">{error}</p>}
        {saved && <p className="toast">{saved}</p>}
        <div className="popup-actions">
          <button className="btn primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save settings"}</button>
        </div>
      </form>
    </section>
  );
}
