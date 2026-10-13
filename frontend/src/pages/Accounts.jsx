import { useCallback, useEffect, useState } from "react";
import {
  addAccount, ago, compact, deleteAccount, duration, editAccount, FORMAT_LABEL, getAccounts, getDna, NOT_CONFIGURED_TEXT, num, PLATFORM_LABEL,
} from "../api";
import ChannelInput from "../components/ChannelInput";
import ProfileInput from "../components/ProfileInput";
import { PostMini } from "../components/Evidence";
import PlatformConnections from "../components/PlatformConnections";
import PlatformIcon from "../components/PlatformIcon";
import Popup from "../components/Popup";
import { Empty, Loading, PageHead } from "../components/ui";

const EMPTY = { name: "", platform: "youtube", source: "", is_us: false, group: "" };
// Older API versions send no health; fall back to the refresh error, if any.
const health = (a) => a.health || (a.last_error
  ? { state: "failed", label: "Last refresh failed", detail: a.last_error }
  : { state: a.last_fetched_at ? "ok" : "pending", label: a.last_fetched_at ? "Collecting" : "Not refreshed yet", detail: null });
const HEALTH_TONE = { ok: "good", limited: "warn", failed: "bad", pending: "neutral", not_configured: "neutral", unverified: "warn" };
const PLACEHOLDER = { youtube: null, rss: "https://…/rss", instagram: "@username or instagram.com/username",
  facebook: "Page name or facebook.com/PageName", x: "@username or x.com/username" };

function Stat({ label, children }) {
  return <div><span>{label}</span><b>{children}</b></div>;
}

function DnaProfile({ p, onNavigate }) {
  if (!p.posts) return <p className="muted">{p.summary[0]}</p>;
  const top = p.formats[0];
  return (
    <div className="dna">
      <ul className="dna-summary">{p.summary.map((s) => <li key={s}>{s}</li>)}</ul>
      <div className="meta-grid">
        <Stat label="Posts per week">{p.per_week} <span className="muted small">({p.posts} posts in {p.span_days} days)</span></Stat>
        <Stat label="Main format">{top ? `${FORMAT_LABEL[top.format] || top.format} (${top.share}%)` : "–"}</Stat>
        {p.account.platform === "youtube" && (
          <>
            <Stat label="Typical length">{p.median_duration_seconds ? duration(p.median_duration_seconds) : "Not available"}</Stat>
            <Stat label="Typical views">{num(p.median_views)} <span className="muted small">({p.views_sample} videos)</span></Stat>
            <Stat label="Engagement">{p.engagement_rate === null ? "Not available" : `${p.engagement_rate}%`}{p.likes_hidden > 0 && <span className="muted small"> · likes hidden on {p.likes_hidden}</span>}</Stat>
          </>
        )}
        <Stat label="Average title">{p.avg_title_words} words</Stat>
      </div>

      {p.main_topics.length > 0 && (
        <div className="ev-block">
          <h4>Main topics</h4>
          <div className="chips">{p.main_topics.map((t) => <span key={t.topic} className="chip static">{t.topic} <span className="chip-count">{t.posts}</span></span>)}</div>
        </div>
      )}
      {p.formats.length > 1 && (
        <div className="ev-block">
          <h4>Formats</h4>
          <div className="chips">{p.formats.map((f) => <span key={f.format} className="chip static">{FORMAT_LABEL[f.format] || f.format} <span className="chip-count">{f.posts} · {f.share}%</span></span>)}</div>
        </div>
      )}
      {p.title_patterns.length > 0 && (
        <div className="ev-block">
          <h4>Common title patterns</h4>
          <div className="table-wrap">
            <table className="compact-table">
              <thead><tr><th>Pattern</th><th className="num">Share</th><th>vs usual views</th><th>Example</th></tr></thead>
              <tbody>
                {p.title_patterns.map((t) => (
                  <tr key={t.pattern}>
                    <td>{t.label}</td>
                    <td className="num">{t.share}% <span className="muted small">({t.posts})</span></td>
                    <td className="small">{t.median_relative !== null && t.others_median_relative !== null ? `${t.median_relative}× vs ${t.others_median_relative}× for other titles` : <span className="muted">Too few posts with views</span>}</td>
                    <td className="small muted">{t.examples[0]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {p.topic_shift && (p.topic_shift.new.length > 0 || p.topic_shift.faded.length > 0) && (
        <div className="ev-block">
          <h4>How topics changed</h4>
          <p className="small">
            {p.topic_shift.new.length > 0 && <>New recently: {p.topic_shift.new.map((t) => `"${t.topic}" (${t.posts})`).join(", ")}. </>}
            {p.topic_shift.faded.length > 0 && <>Less often: {p.topic_shift.faded.map((t) => `"${t.topic}"`).join(", ")}.</>}
            <span className="muted"> Comparing {p.topic_shift.recent_posts} recent with {p.topic_shift.earlier_posts} earlier posts.</span>
          </p>
        </div>
      )}
      {p.standouts.length > 0 && (
        <div className="ev-block">
          <h4>Posts far above their usual ({p.standout_count})</h4>
          <div className="post-mini-list">{p.standouts.map((x) => <PostMini key={x.id} p={x} />)}</div>
        </div>
      )}
      <details className="evidence">
        <summary>Recent posts and limitations</summary>
        <div className="post-mini-list">{p.recent_posts.map((x) => <PostMini key={x.id} p={x} />)}</div>
        <ul className="limits">{p.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </details>
      {!p.account.is_us && (
        <div className="card-actions"><button className="btn ghost small-btn" onClick={() => onNavigate?.("explorer")}>Explore their posts →</button></div>
      )}
    </div>
  );
}

function DnaDialog({ orgId, account, onClose, onNavigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getDna(orgId, account.id).then(setData).catch((e) => setError(e.message));
  }, [orgId, account.id]);
  return (
    <Popup title={`Content DNA: ${account.name}`} onClose={onClose} wide>
      <p className="muted small">What this account published in the last {data?.days || 90} days, from its public posts only.</p>
      {error ? <p className="error-text">{error}</p> : !data ? <Loading what="Reading their posts…" /> : <DnaProfile p={data.profiles[0]} onNavigate={(t) => { onClose(); onNavigate?.(t); }} />}
    </Popup>
  );
}

function DnaCompare({ orgId, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getDna(orgId).then(setData).catch((e) => setError(e.message));
  }, [orgId]);
  const rows = [
    ["Posts per week", (p) => p.per_week ?? "–"],
    ["Posts (last 90 days)", (p) => p.posts],
    ["Main format", (p) => (p.formats?.[0] ? `${FORMAT_LABEL[p.formats[0].format] || p.formats[0].format} (${p.formats[0].share}%)` : "–")],
    ["Typical length", (p) => (p.median_duration_seconds ? duration(p.median_duration_seconds) : "–")],
    ["Typical views", (p) => (p.account.platform === "youtube" ? num(p.median_views) : "Not reported")],
    ["Engagement", (p) => (p.engagement_rate === null || p.engagement_rate === undefined ? "–" : `${p.engagement_rate}%`)],
    ["Top topics", (p) => (p.main_topics || []).slice(0, 3).map((t) => t.topic).join(", ") || "–"],
    ["Common title pattern", (p) => (p.title_patterns?.[0] ? `${p.title_patterns[0].label} (${p.title_patterns[0].share}%)` : "–")],
    ["Standout posts (2×+)", (p) => p.standout_count ?? 0],
    ["Enough data?", (p) => (p.enough_data ? "Yes" : "Early signs only")],
  ];
  return (
    <Popup title="Compare Content DNA" onClose={onClose} wide>
      {error ? <p className="error-text">{error}</p> : !data ? <Loading what="Reading every account's posts…" /> : (
        <>
          <div className="table-wrap">
            <table className="compare-table">
              <thead><tr><th></th>{data.profiles.map((p) => <th key={p.account.id}>{p.account.name}{p.account.is_us && " (you)"}<div className="muted tiny-text">{PLATFORM_LABEL[p.account.platform]}</div></th>)}</tr></thead>
              <tbody>
                {rows.map(([label, fn]) => (
                  <tr key={label}><td className="muted small nowrap">{label}</td>{data.profiles.map((p) => <td key={p.account.id} className="small">{fn(p)}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small">Raw views depend on channel size; compare patterns and "standout posts" rather than totals. Based on public data only.</p>
        </>
      )}
    </Popup>
  );
}

function EditDialog({ orgId, account, groups, onSaved, onClose }) {
  const [form, setForm] = useState({ name: account.name, source: account.source, group: account.group || "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const changedSource = form.source.trim() !== account.source;
  async function save() {
    setBusy(true);
    try {
      await editAccount(orgId, account.id, { name: form.name, group: form.group || null, ...(changedSource && { source: form.source }) });
      onSaved();
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Popup title={`Edit ${account.name}`} onClose={onClose}>
      <label className="field"><span>Name</span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} maxLength={80} /></label>
      {!account.is_us && (
        <label className="field"><span>Group</span>
          <select value={form.group} onChange={(e) => setForm({ ...form, group: e.target.value })}>
            <option value="">No group</option>
            {groups.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
          </select>
        </label>
      )}
      <label className="field"><span>{account.platform === "youtube" ? "YouTube handle or link" : "RSS link"}</span>
        <input value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} />
        {changedSource && <small className="warn-text">The new link is checked before saving. If it's a different account, its old posts are removed.</small>}
      </label>
      {error && <p className="error-text">{error}</p>}
      <div className="popup-actions">
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" onClick={save} disabled={busy}>{busy ? "Checking…" : "Save"}</button>
      </div>
    </Popup>
  );
}

export default function Accounts({ orgId, onChanged, platforms, groups = [], refreshKey, onNavigate }) {
  const [list, setList] = useState(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState(EMPTY);
  const [formError, setFormError] = useState("");
  const [formNote, setFormNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [dialog, setDialog] = useState(null); // {mode: "dna" | "edit" | "remove" | "compare", account}

  const load = useCallback(async () => {
    try {
      setList(await getAccounts(orgId));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, [orgId]);

  useEffect(() => { load(); }, [load, refreshKey]);

  async function onSubmit(e) {
    e.preventDefault();
    const source = form.source.trim();
    if (!source || (!form.name.trim() && !isSocial)) {
      setFormError(isSocial ? `Enter ${sourceLabel.toLowerCase()}.` : `Enter a name and ${sourceLabel.toLowerCase()}.`);
      return;
    }
    if (form.platform === "rss" && !/^https?:\/\//i.test(source)) {
      setFormError("The RSS link must start with http:// or https://");
      return;
    }
    setSaving(true);
    try {
      const added = await addAccount(orgId, { ...form, name: form.name.trim(), source, group: form.is_us ? null : form.group || null });
      setFormNote(added.verified === false
        ? `${added.name} was saved as Unverified: ${added.note || "it's checked with the platform once the integration is configured and connected."}`
        : "");
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

  async function remove(account) {
    try {
      await deleteAccount(orgId, account.id);
      setDialog(null);
      await load();
      onChanged();
    } catch (e) {
      setError(e.message);
    }
  }

  const isYT = form.platform === "youtube";
  const isSocial = ["instagram", "facebook", "x"].includes(form.platform);
  const sourceLabel = platforms?.supported?.find((p) => p.id === form.platform)?.source_label || (isYT ? "YouTube channel" : "RSS link");
  const competitors = (list || []).filter((a) => !a.is_us).length;

  return (
    <section className="panel">
      <PageHead
        title="Accounts"
        what='Add your own accounts (tick "Ours") and the competitors to compare against. Use the same name for one competitor on different platforms.'
        next="Open Content DNA to see what an account publishes."
      >
        {competitors > 0 && <button className="btn ghost small-btn" onClick={() => setDialog({ mode: "compare" })}>Compare Content DNA</button>}
      </PageHead>

      <PlatformConnections orgId={orgId} onChanged={() => { load(); onChanged(); }} />

      <h3 className="sub-head">Add an account</h3>
      <form className={`add-form ${isSocial ? "with-notes" : ""}`} onSubmit={onSubmit} noValidate>
        <label className="field">
          <span>Platform</span>
          <select id="acc-platform" value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })}>
            {(platforms?.supported || [{ id: "youtube", label: "YouTube" }, { id: "rss", label: "Website / blog (RSS)" }]).map((p) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Name</span>
          <input id="acc-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder={isSocial ? "Filled from the profile" : "e.g. the creator or brand name"} />
        </label>
        <div className="field grow">
          <label htmlFor="acc-source">{sourceLabel}</label>
          {isYT ? (
            <ChannelInput
              id="acc-source"
              value={form.source}
              onChange={(source) => setForm((f) => ({ ...f, source }))}
              onPick={(ch) => setForm((f) => ({ ...f, source: ch.handle || ch.channel_id, name: f.name.trim() ? f.name : ch.title }))}
            />
          ) : isSocial ? (
            <ProfileInput
              key={form.platform}
              id="acc-source"
              orgId={orgId}
              platform={form.platform}
              label={PLATFORM_LABEL[form.platform]}
              value={form.source}
              placeholder={PLACEHOLDER[form.platform]}
              onChange={(source) => setForm((f) => ({ ...f, source }))}
              onPick={(p) => setForm((f) => ({ ...f, source: p.source, name: f.name.trim() ? f.name : p.display_name || p.source }))}
            />
          ) : (
            <input id="acc-source" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} placeholder={PLACEHOLDER[form.platform] || ""} />
          )}
        </div>
        {!form.is_us && groups.length > 0 && (
          <label className="field">
            <span>Group (optional)</span>
            <select value={form.group} onChange={(e) => setForm({ ...form, group: e.target.value })}>
              <option value="">No group</option>
              {groups.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
            </select>
          </label>
        )}
        <label className="check">
          <input id="acc-us" type="checkbox" checked={form.is_us} onChange={(e) => setForm({ ...form, is_us: e.target.checked })} />
          Ours
        </label>
        <button className="btn primary" type="submit" disabled={saving}>{saving ? "Checking…" : "Add"}</button>
      </form>
      {formError && <p className="error-text" role="alert">{formError}</p>}
      {formNote && <p className="notice small">{formNote}</p>}
      {platforms?.planned?.length > 0 && (
        <p className="muted small">Not connected yet: {platforms.planned.map((p) => p.label).join(", ")}. See Workspace settings for what each one needs.</p>
      )}

      {error ? (
        <Empty title="Accounts not available">{error}</Empty>
      ) : !list ? (
        <Loading what="Loading accounts…" />
      ) : list.length === 0 ? (
        <Empty title="No accounts yet">Add your own account first (tick "Ours"), then 3–5 competitors.</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Account</th><th>Platform</th><th className="num">Posts</th><th className="num" title="Subscribers (YouTube) or followers">Audience</th><th>Data</th><th></th></tr>
            </thead>
            <tbody>
              {list.map((a) => (
                <tr key={a.id}>
                  <td>
                    <span className="acc-name">
                      {a.thumbnail ? <img src={a.thumbnail} alt="" className="logo" /> : <span className={`logo placeholder ${a.platform}`} />}
                      <span>
                        <b>{a.name}</b>{" "}
                        {a.is_us ? <span className="pill good tiny">Ours</span> : <span className="pill neutral tiny">{a.group_label || "Competitor"}</span>}
                        <div className="muted tiny-text link-cell">{a.source}</div>
                      </span>
                    </span>
                  </td>
                  <td><span className="plat-cell"><PlatformIcon platform={a.platform} size={16} />{PLATFORM_LABEL[a.platform] || a.platform}</span></td>
                  <td className="num">{a.posts}</td>
                  <td className="num">{a.subscribers !== null && a.subscribers !== undefined ? compact(a.subscribers) : <span className="muted small">Not reported</span>}</td>
                  <td>
                    <span className={`pill tiny ${HEALTH_TONE[health(a).state]}`} title={health(a).detail || ""}>{health(a).label}</span>
                    <div className="muted tiny-text">{a.last_fetched_at ? `Refreshed ${ago(a.last_fetched_at)}` : "Never refreshed"}</div>
                    {health(a).state !== "ok" && health(a).detail && (
                      <div className="muted tiny-text wrap">{health(a).state === "not_configured" ? NOT_CONFIGURED_TEXT : health(a).detail}</div>
                    )}
                  </td>
                  <td>
                    <div className="row-actions">
                      {a.public_url && <a className="btn ghost small-btn" href={a.public_url} target="_blank" rel="noreferrer">Open ↗</a>}
                      <button className="btn ghost small-btn" onClick={() => setDialog({ mode: "dna", account: a })}>Content DNA</button>
                      <button className="btn ghost small-btn" onClick={() => setDialog({ mode: "edit", account: a })}>Edit</button>
                      <button className="btn ghost small-btn" onClick={() => setDialog({ mode: "remove", account: a })}>Remove</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {dialog?.mode === "dna" && <DnaDialog orgId={orgId} account={dialog.account} onClose={() => setDialog(null)} onNavigate={onNavigate} />}
      {dialog?.mode === "compare" && <DnaCompare orgId={orgId} onClose={() => setDialog(null)} />}
      {dialog?.mode === "edit" && (
        <EditDialog orgId={orgId} account={dialog.account} groups={groups} onClose={() => setDialog(null)} onSaved={() => { load(); onChanged(); }} />
      )}
      {dialog?.mode === "remove" && (
        <Popup title={`Remove ${dialog.account.name}?`} onClose={() => setDialog(null)}>
          <p>This deletes the account and all of its collected posts and history in this workspace. It can't be undone.</p>
          <div className="popup-actions">
            <button className="btn ghost" onClick={() => setDialog(null)}>Cancel</button>
            <button className="btn danger" onClick={() => remove(dialog.account)}>Remove account</button>
          </div>
        </Popup>
      )}
    </section>
  );
}
