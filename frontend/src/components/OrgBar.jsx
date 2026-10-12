import { useState } from "react";
import { addOrganization } from "../api";

const CATEGORIES = ["News", "Fitness", "Technology", "Food", "Travel", "Gaming", "Fashion & Beauty", "Education", "Business", "Other"];

// Organization picker plus an "Add organization" form.
export default function OrgBar({ orgs, orgId, onSelect, onAdded }) {
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", category: "News" });
  const [error, setError] = useState("");

  async function onSubmit(e) {
    e.preventDefault();
    if (!form.name.trim()) {
      setError("Enter an organization name.");
      return;
    }
    try {
      // News moves fast, so compare the last 24 hours. Creators post less often, so use 30 days.
      const window_hours = form.category === "News" ? 24 : 24 * 30;
      const org = await addOrganization({ name: form.name.trim(), category: form.category, window_hours });
      setForm({ name: "", category: "News" });
      setError("");
      setAdding(false);
      onAdded(org);
    } catch (err) {
      setError(err.message);
    }
  }

  const current = orgs.find((o) => o.id === orgId);

  return (
    <div className="orgbar">
      <label className="org-select">
        <span>Organization</span>
        <select id="org-select" value={orgId ?? ""} onChange={(e) => onSelect(Number(e.target.value))}>
          {orgs.length === 0 && <option value="">No organizations yet</option>}
          {orgs.map((o) => (
            <option key={o.id} value={o.id}>{o.name}</option>
          ))}
        </select>
      </label>
      {current && (
        <span className="org-meta">
          {current.category} · comparing the last {current.window_hours >= 48 ? `${Math.round(current.window_hours / 24)} days` : `${current.window_hours} hours`}
        </span>
      )}
      {!adding ? (
        <button className="btn ghost small-btn" onClick={() => setAdding(true)}>+ Add organization</button>
      ) : (
        <form className="org-form" onSubmit={onSubmit} noValidate>
          <input id="org-name" placeholder="Organization name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <select id="org-category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
          <button className="btn primary small-btn" type="submit">Add</button>
          <button className="btn ghost small-btn" type="button" onClick={() => { setAdding(false); setError(""); }}>Cancel</button>
          {error && <span className="error-text">{error}</span>}
        </form>
      )}
    </div>
  );
}
