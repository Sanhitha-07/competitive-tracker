import { useEffect, useState } from "react";
import { compact, duration, fmtTime, FORMAT_LABEL, getContent, METRIC_WORD, PLATFORM_LABEL } from "../api";
import Popup from "../components/Popup";

const PAGE = 24;
const MAX_COMPARE = 4;
const EMPTY = {
  account_id: "", platform: "", topic: "", format: "", since: "", until: "", performance: "",
  q: "", my_topics: false, include_ours: false, sort: "newest",
};

function engagement(p) {
  if (!p.views || p.likes == null) return null;
  return (((p.likes || 0) + (p.comments || 0)) / p.views * 100).toFixed(2);
}

function Card({ p, selected, onToggle, disabled }) {
  return (
    <article className={`gallery-card ${selected ? "selected" : ""}`}>
      <a href={p.link} target="_blank" rel="noreferrer" className="thumb">
        {p.thumbnail ? <img src={p.thumbnail} alt="" loading="lazy" /> : <span className="thumb-ph">{FORMAT_LABEL[p.format] || PLATFORM_LABEL[p.platform]}</span>}
        {p.duration_seconds ? <span className="dur">{duration(p.duration_seconds)}</span> : null}
      </a>
      <div className="gallery-body">
        <a href={p.link} target="_blank" rel="noreferrer" className="gallery-title">{p.title}</a>
        <span className="muted small">
          {p.account}{p.is_us && <span className="pill good tiny">Ours</span>} · {fmtTime(p.published_at)}
        </span>
        <div className="plats">
          <span className={`plat ${p.platform}`}>{PLATFORM_LABEL[p.platform] || p.platform}</span>
          {p.format && <span className="plat fmt">{FORMAT_LABEL[p.format] || p.format}</span>}
          {p.relative != null && (
            <span className={`plat rel ${p.relative >= 2 ? "hot" : p.relative >= 1.2 ? "up" : p.relative < 0.8 ? "down" : ""}`}
              title={`${METRIC_WORD[p.platform] || "views"} ÷ ${p.account}'s usual ${p.baseline_views?.toLocaleString("en-IN")} (median of ${p.baseline_posts} posts)`}>
              {p.relative}× usual
            </span>
          )}
        </div>
        {(p.views != null || p.interactions != null) && (
          <span className="small">
            {[p.views != null && `${compact(p.views)} views`, p.likes != null && `${compact(p.likes)} ${p.platform === "facebook" ? "reactions" : "likes"}`,
              p.comments != null && `${compact(p.comments)} comments`, p.shares != null && `${compact(p.shares)} shares`].filter(Boolean).join(" · ")}
          </span>
        )}
        {p.topics?.length > 0 && <div className="chips">{p.topics.slice(0, 4).map((t) => <span key={t} className="chip static tiny">{t}</span>)}</div>}
        <label className="check small compare-check">
          <input type="checkbox" checked={selected} disabled={disabled && !selected} onChange={onToggle} /> Compare
        </label>
      </div>
    </article>
  );
}

function Compare({ items, onClose }) {
  const rows = [
    ["Account", (p) => p.account],
    ["Published", (p) => fmtTime(p.published_at)],
    ["Platform", (p) => PLATFORM_LABEL[p.platform] || p.platform],
    ["Format", (p) => FORMAT_LABEL[p.format] || p.format || "–"],
    ["Length", (p) => duration(p.duration_seconds)],
    ["Views", (p) => (p.views != null ? p.views.toLocaleString("en-IN") : "not public")],
    ["Shares", (p) => (p.shares != null ? p.shares.toLocaleString("en-IN") : "n.a.")],
    ["Likes", (p) => (p.likes != null ? p.likes.toLocaleString("en-IN") : "hidden / n.a.")],
    ["Comments", (p) => (p.comments != null ? p.comments.toLocaleString("en-IN") : "n.a.")],
    ["Engagement per view", (p) => (engagement(p) ? `${engagement(p)}%` : "–")],
    ["Interactions", (p) => (p.interactions != null ? p.interactions.toLocaleString("en-IN") : "–")],
    ["vs account's usual", (p) => (p.relative != null ? `${p.relative}×` : "–")],
    ["Account's usual", (p) => (p.baseline_views != null ? `${p.baseline_views.toLocaleString("en-IN")} ${METRIC_WORD[p.platform] || "views"} (${p.baseline_posts} posts)` : "–")],
    ["Topics", (p) => (p.topics || []).join(", ") || "–"],
    ["Metrics as of", (p) => fmtTime(p.metrics_updated_at)],
  ];
  return (
    <Popup title="Side-by-side comparison" onClose={onClose} wide>
      <div className="table-wrap">
        <table className="compare-table">
          <thead>
            <tr>
              <th></th>
              {items.map((p) => (
                <th key={p.id}>
                  {p.thumbnail && <img src={p.thumbnail} alt="" className="cmp-thumb" />}
                  <a href={p.link} target="_blank" rel="noreferrer">{p.title}</a>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, fn]) => (
              <tr key={label}><td className="muted small nowrap">{label}</td>{items.map((p) => <td key={p.id}>{fn(p)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        Engagement per view = (likes + comments) ÷ views. "vs account's usual" compares each post with its own account (views on YouTube,
        interactions on Instagram and Facebook), so accounts of different sizes and platforms can be compared. Numbers keep growing after publishing, so newer posts are at a disadvantage.
      </p>
    </Popup>
  );
}

export default function Explorer({ orgId, refreshKey }) {
  const [filters, setFilters] = useState(EMPTY);
  const [search, setSearch] = useState("");
  const [data, setData] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState([]);
  const [comparing, setComparing] = useState(false);

  // Wait for typing to pause before searching.
  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => (f.q === search ? f : { ...f, q: search })), 400);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const params = { ...filters, limit: PAGE, offset: 0 };
    if (params.since) params.since = new Date(params.since).toISOString();
    if (params.until) params.until = new Date(`${params.until}T23:59:59`).toISOString();
    getContent(orgId, params)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setItems(d.items);
        setError("");
      })
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [orgId, filters, refreshKey]);

  useEffect(() => setSelected([]), [orgId]);

  async function more() {
    setLoading(true);
    try {
      const params = { ...filters, limit: PAGE, offset: items.length };
      if (params.since) params.since = new Date(params.since).toISOString();
      if (params.until) params.until = new Date(`${params.until}T23:59:59`).toISOString();
      const d = await getContent(orgId, params);
      setItems((cur) => [...cur, ...d.items]);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const set = (k) => (e) => setFilters({ ...filters, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const toggle = (p) => setSelected((cur) => (cur.some((x) => x.id === p.id) ? cur.filter((x) => x.id !== p.id) : [...cur, p]));
  const f = data?.facets;
  const active = Object.entries(filters).some(([k, v]) => v !== EMPTY[k]);

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Content Explorer</h2>
          <p className="muted">Every competitor post collected from connected platforms, with public metrics. Filter, open the source, or tick up to {MAX_COMPARE} to compare side by side.</p>
        </div>
        <input className="search" placeholder="Search titles and tags…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search" />
      </div>

      <div className="filters">
        <select value={filters.account_id} onChange={set("account_id")} aria-label="Competitor">
          <option value="">All accounts</option>
          {f?.accounts.filter((a) => filters.include_ours || !a.is_us).map((a) => (
            <option key={a.id} value={a.id}>{a.name} ({PLATFORM_LABEL[a.platform] || a.platform})</option>
          ))}
        </select>
        <select value={filters.platform} onChange={set("platform")} aria-label="Platform">
          <option value="">All platforms</option>
          {f?.platforms.map((p) => <option key={p} value={p}>{PLATFORM_LABEL[p] || p}</option>)}
        </select>
        <select value={filters.format} onChange={set("format")} aria-label="Format">
          <option value="">All formats</option>
          {f?.formats.map((x) => <option key={x} value={x}>{FORMAT_LABEL[x] || x}</option>)}
        </select>
        <input list="topic-list" value={filters.topic} onChange={set("topic")} placeholder="Topic" aria-label="Topic" />
        <datalist id="topic-list">{f?.topics.map((t) => <option key={t} value={t} />)}</datalist>
        <select value={filters.performance} onChange={set("performance")} aria-label="Performance">
          <option value="">Any performance</option>
          <option value="outlier">2×+ account's usual</option>
          <option value="above">1.2×+ usual</option>
          <option value="usual">About usual</option>
          <option value="below">Below usual</option>
          <option value="unknown">No view data</option>
        </select>
        <label className="date-f">From <input type="date" value={filters.since} onChange={set("since")} /></label>
        <label className="date-f">To <input type="date" value={filters.until} onChange={set("until")} /></label>
        <select value={filters.sort} onChange={set("sort")} aria-label="Sort">
          <option value="newest">Newest</option>
          <option value="views">Most views / interactions</option>
          <option value="relative">Most above usual</option>
        </select>
        <label className="check small" title={f?.my_topics?.length ? f.my_topics.join(", ") : "Add topics in Workspace settings"}>
          <input type="checkbox" checked={filters.my_topics} onChange={set("my_topics")} disabled={!f?.my_topics?.length} /> My niche topics
        </label>
        <label className="check small"><input type="checkbox" checked={filters.include_ours} onChange={set("include_ours")} /> Include our posts</label>
        {active && <button className="btn ghost small-btn" onClick={() => { setFilters(EMPTY); setSearch(""); }}>Clear filters</button>}
      </div>

      {selected.length > 0 && (
        <div className="compare-bar">
          <span>{selected.length} selected</span>
          <button className="btn primary small-btn" disabled={selected.length < 2} onClick={() => setComparing(true)}>Compare side by side</button>
          <button className="btn ghost small-btn" onClick={() => setSelected([])}>Clear</button>
        </div>
      )}

      {error ? (
        <div className="empty"><b>Content not available</b><span>{error}</span></div>
      ) : !data ? (
        <div className="empty"><b>Loading…</b></div>
      ) : items.length === 0 ? (
        <div className="empty"><b>No posts match</b><span>{data.total === 0 && !active ? "Add competitors in Accounts and click Refresh." : "Try removing a filter."}</span></div>
      ) : (
        <>
          <p className="muted small">{data.total} post{data.total !== 1 ? "s" : ""}{loading && " · loading…"}</p>
          <div className="gallery">
            {items.map((p) => (
              <Card key={p.id} p={p} selected={selected.some((x) => x.id === p.id)} disabled={selected.length >= MAX_COMPARE} onToggle={() => toggle(p)} />
            ))}
          </div>
          {items.length < data.total && (
            <div className="center"><button className="btn ghost" onClick={more} disabled={loading}>{loading ? "Loading…" : "Load more"}</button></div>
          )}
        </>
      )}
      {comparing && <Compare items={selected} onClose={() => setComparing(false)} />}
    </section>
  );
}
