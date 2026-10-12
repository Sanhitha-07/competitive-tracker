import { useState } from "react";
import { addOrganization, period } from "../api";

// Workspace picker plus an "Add workspace" form. Full settings live in the Workspace tab.
export default function OrgBar({ orgs, orgId, config, options, onSelect, onAdded }) {
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", creator_type: "", category: "other" });
  const [error, setError] = useState("");

  async function onSubmit(e) {
    e.preventDefault();
    if (!form.name.trim()) return setError("Enter a name.");
    if (!form.creator_type) return setError("Choose a type.");
    try {
      // The industry sets the starting comparison window (news: 24 hours, most creators: 2–4 weeks).
      const org = await addOrganization({ ...form, name: form.name.trim() });
      setForm({ name: "", creator_type: "", category: "other" });
      setError("");
      setAdding(false);
      onAdded(org);
    } catch (err) {
      setError(err.message);
    }
  }

  const typeLabel = options?.creator_types.find((c) => c.id === config?.creator_type)?.label;

  return (
    <div className="orgbar">
      <label className="org-select">
        <span>Workspace</span>
        <select id="org-select" value={orgId ?? ""} onChange={(e) => onSelect(Number(e.target.value))}>
          {orgs.length === 0 && <option value="">No workspaces yet</option>}
          {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
      </label>
      {config && (
        <span className="org-meta">
          {[typeLabel, config.industry_label, config.niche && config.industry !== "other" ? config.niche : null].filter(Boolean).join(" · ")}
          {" · comparing "}{period(config.window_hours)}
          {!config.configured && <span className="pill warn tiny">Settings incomplete</span>}
        </span>
      )}
      {!adding ? (
        <button className="btn ghost small-btn" onClick={() => setAdding(true)}>+ Add workspace</button>
      ) : (
        <form className="org-form" onSubmit={onSubmit} noValidate>
          <input id="org-name" placeholder="Name (you, a client, a brand)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <select id="org-type" value={form.creator_type} onChange={(e) => setForm({ ...form, creator_type: e.target.value })} aria-label="Type">
            <option value="">Type…</option>
            {options?.creator_types.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
          <select id="org-category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} aria-label="Industry">
            {options?.industries.map((i) => <option key={i.id} value={i.id}>{i.label}</option>)}
          </select>
          <button className="btn primary small-btn" type="submit">Add</button>
          <button className="btn ghost small-btn" type="button" onClick={() => { setAdding(false); setError(""); }}>Cancel</button>
          {error && <span className="error-text">{error}</span>}
        </form>
      )}
    </div>
  );
}
