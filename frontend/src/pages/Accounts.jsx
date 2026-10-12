import { useEffect, useState } from "react";
import { addAccount, compact, deleteAccount, getAccounts, PLATFORM_LABEL } from "../api";
import ChannelInput from "../components/ChannelInput";

const EMPTY = { name: "", platform: "youtube", source: "", is_us: false };

export default function Accounts({ orgId, onChanged }) {
  const [list, setList] = useState([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState(EMPTY);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  async function load() {
    try {
      setList(await getAccounts(orgId));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);

  async function onSubmit(e) {
    e.preventDefault();
    const source = form.source.trim();
    if (!form.name.trim() || !source) {
      setFormError(form.platform === "youtube" ? "Enter a name and a YouTube handle." : "Enter a name and an RSS link.");
      return;
    }
    if (form.platform === "rss" && !/^https?:\/\//i.test(source)) {
      setFormError("The RSS link must start with http:// or https://");
      return;
    }
    setSaving(true);
    try {
      await addAccount(orgId, { ...form, name: form.name.trim(), source });
      setForm({ ...EMPTY, platform: form.platform });
      setFormError("");
      await load();
      onChanged();
    } catch (e2) {
      setFormError(e2.message);
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(id) {
    try {
      await deleteAccount(orgId, id);
      await load();
      onChanged();
    } catch (e) {
      setError(e.message);
    }
  }

  const isYT = form.platform === "youtube";

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Accounts</h2>
          <p className="muted">Our own accounts and the competitors we compare against. Use the same name for one competitor's website and YouTube channel.</p>
        </div>
      </div>

      <form className="add-form" onSubmit={onSubmit} noValidate>
        <label className="field">
          <span>Platform</span>
          <select id="acc-platform" value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })}>
            <option value="youtube">YouTube channel</option>
            <option value="rss">News website (RSS)</option>
          </select>
        </label>
        <label className="field">
          <span>Name</span>
          <input id="acc-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. NDTV" />
        </label>
        <div className="field grow">
          <label htmlFor="acc-source">{isYT ? "YouTube channel (name, @handle or link)" : "RSS link"}</label>
          {isYT ? (
            <ChannelInput
              id="acc-source"
              value={form.source}
              onChange={(source) => setForm((f) => ({ ...f, source }))}
              onPick={(ch) =>
                setForm((f) => ({
                  ...f,
                  source: ch.handle || ch.channel_id,
                  name: f.name.trim() ? f.name : ch.title,
                }))
              }
            />
          ) : (
            <input
              id="acc-source"
              value={form.source}
              onChange={(e) => setForm({ ...form, source: e.target.value })}
              placeholder="https://…/rss"
            />
          )}
        </div>
        <label className="check">
          <input id="acc-us" type="checkbox" checked={form.is_us} onChange={(e) => setForm({ ...form, is_us: e.target.checked })} />
          Ours
        </label>
        <button className="btn primary" type="submit" disabled={saving}>{saving ? "Checking…" : "Add"}</button>
      </form>
      {formError && <p className="error-text">{formError}</p>}

      {error ? (
        <div className="empty"><b>Accounts not available</b><span>{error}</span></div>
      ) : list.length === 0 ? (
        <div className="empty"><b>No accounts yet</b><span>Add our own account first (tick "Ours"), then 3–5 competitors.</span></div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Name</th><th>Platform</th><th>Link or handle</th><th>Subscribers</th><th>Status</th><th></th></tr>
            </thead>
            <tbody>
              {list.map((a) => (
                <tr key={a.id}>
                  <td>
                    <span className="acc-name">
                      {a.thumbnail ? <img src={a.thumbnail} alt="" className="logo" /> : <span className={`logo placeholder ${a.platform}`} />}
                      <b>{a.name}</b>
                      {a.is_us ? <span className="pill good">Ours</span> : <span className="pill neutral">Competitor</span>}
                    </span>
                  </td>
                  <td><span className={`plat ${a.platform}`}>{PLATFORM_LABEL[a.platform]}</span></td>
                  <td className="link-cell">{a.source}</td>
                  <td className="num">{a.platform === "youtube" ? compact(a.subscribers) : "–"}</td>
                  <td>{a.last_error ? <span className="pill bad" title={a.last_error}>Last refresh failed</span> : <span className="muted small">OK</span>}</td>
                  <td><button className="btn ghost small-btn" onClick={() => onDelete(a.id)}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
