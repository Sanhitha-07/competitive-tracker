import { useEffect, useState } from "react";
import {
  ALL_PLATFORMS, compact, duration, fmtTime, FORMAT_LABEL, getContent, PLATFORM_LABEL, removeFromCollection, saveToCollection,
} from "../api";
import Popup from "../components/Popup";
import { BriefButton, Empty, Loading, PageHead } from "../components/ui";

const PAGE = 24;
const MAX_COMPARE = 4;
// Fields an older API version doesn't send get safe empty values, so the page never crashes on them.
function withDefaults(d) {
  const items = (d.items || []).map((p) => ({ saved_in: [], engagement_rate: null, topics: [], ...p }));
  return { ...d, items, facets: { collections: [], accounts: [], platforms: [], formats: [], topics: [], my_topics: [], ...(d.facets || {}) } };
}

const EMPTY = {
  account_id: "", platform: "", topic: "", format: "", since: "", until: "", performance: "",
  q: "", my_topics: false, include_ours: false, collection: "", sort: "newest",
};

function SaveMenu({ orgId, p, collections, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [newName, setNewName] = useState(null);
  async function act(value) {
    if (!value) return;
    if (value === "__new") return setNewName("");
    setBusy(true);
    try {
      const saved = p.saved_in.find((s) => s.collection === value);
      if (saved) {
        await removeFromCollection(orgId, saved.id);
        onChanged(p.id, p.saved_in.filter((s) => s !== saved), value, -1);
      } else {
        const item = await saveToCollection(orgId, value, p.id);
        onChanged(p.id, [...p.saved_in, { id: item.id, collection: value }], value, 1);
      }
    } finally {
      setBusy(false);
    }
  }
  if (newName !== null) {
    return (
      <form className="inline-form" onSubmit={(e) => { e.preventDefault(); if (newName.trim()) { act(newName.trim()); setNewName(null); } }}>
        <input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Collection name" maxLength={60} aria-label="New collection name" />
        <button className="btn ghost small-btn" type="submit">Save</button>
        <button className="icon-btn" type="button" onClick={() => setNewName(null)} aria-label="Cancel">✕</button>
      </form>
    );
  }
  return (
    <select className="save-select" value="" disabled={busy} onChange={(e) => act(e.target.value)} aria-label="Save to a collection">
      <option value="">{p.saved_in.length ? `Saved (${p.saved_in.length})` : "Save…"}</option>
      {collections.map((c) => (
        <option key={c.name} value={c.name}>{p.saved_in.some((s) => s.collection === c.name) ? "✓ " : ""}{c.name}</option>
      ))}
      <option value="__new">+ New collection…</option>
    </select>
  );
}

function Card({ orgId, p, selected, onToggle, disabled, collections, onChanged, onNavigate }) {
  return (
    <article className={`gallery-card ${selected ? "selected" : ""}`}>
      <a href={p.link} target="_blank" rel="noreferrer" className="thumb" aria-label={`Open "${p.title}" on ${PLATFORM_LABEL[p.platform]}`}>
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
          {p.relative !== null && (
            <span className={`plat rel ${p.relative >= 2 ? "hot" : p.relative >= 1.2 ? "up" : p.relative < 0.8 ? "down" : ""}`}
              title={`Views ÷ ${p.account}'s usual ${p.baseline_views?.toLocaleString("en-IN")} (median of ${p.baseline_posts} posts)`}>
              {p.relative}× usual
            </span>
          )}
        </div>
        {p.views !== null ? (
          <span className="small">
            {compact(p.views)} views · {p.likes !== null ? `${compact(p.likes)} likes` : "likes hidden"} · {p.comments !== null ? `${compact(p.comments)} comments` : "comments n/a"}
            {p.engagement_rate !== null && <span className="muted"> · {p.engagement_rate}% eng.</span>}
          </span>
        ) : (
          p.likes !== null || p.comments !== null || p.shares != null ? (
            <span className="small">
              {[p.likes !== null && `${compact(p.likes)} ${p.platform === "facebook" ? "reactions" : "likes"}`,
                p.comments !== null && `${compact(p.comments)} comments`,
                p.shares != null && `${compact(p.shares)} ${p.platform === "x" ? "reposts" : "shares"}`].filter(Boolean).join(" · ")}
              <span className="muted"> · no view count</span>
            </span>
          ) : (
            <span className="muted small">{p.platform === "rss" ? "Feeds don't report views" : "No public counts"}</span>
          )
        )}
        {p.topics?.length > 0 && <div className="chips">{p.topics.slice(0, 4).map((t) => <span key={t} className="chip static tiny">{t}</span>)}</div>}
        <div className="card-tools">
          <label className="check small compare-check">
            <input type="checkbox" checked={selected} disabled={disabled && !selected} onChange={onToggle} /> Compare
          </label>
          <SaveMenu orgId={orgId} p={p} collections={collections} onChanged={onChanged} />
          {!p.is_us && <BriefButton orgId={orgId} source={{ post_id: p.id }} onNavigate={onNavigate} label="Brief" className="btn ghost small-btn" />}
        </div>
      </div>
    </article>
  );
}

function Compare({ items, onClose }) {
  const na = (v, f = (x) => x.toLocaleString("en-IN")) => (v === null || v === undefined ? <span className="muted">Not available</span> : f(v));
  const rows = [
    ["Account", (p) => p.account],
    ["Published", (p) => fmtTime(p.published_at)],
    ["Platform", (p) => PLATFORM_LABEL[p.platform] || p.platform],
    ["Format", (p) => FORMAT_LABEL[p.format] || p.format || "–"],
    ["Length", (p) => na(p.duration_seconds, duration)],
    ["Views", (p) => na(p.views)],
    ["Likes", (p) => (p.likes === null && p.views !== null ? <span className="muted">Hidden by the creator</span> : na(p.likes))],
    ["Comments", (p) => na(p.comments)],
    ["Shares / reposts", (p) => na(p.shares)],
    ["Engagement rate", (p) => na(p.engagement_rate, (v) => `${v}%`)],
    ["vs account's usual", (p) => na(p.relative, (v) => `${v}×`)],
    ["Account's usual views", (p) => (p.baseline_views !== null ? `${p.baseline_views.toLocaleString("en-IN")} (${p.baseline_posts} posts)` : <span className="muted">Not enough history</span>)],
    ["Topics", (p) => (p.topics || []).join(", ") || "–"],
    ["Metrics as of", (p) => (p.metrics_updated_at ? fmtTime(p.metrics_updated_at) : "–")],
  ];
  const platforms = new Set(items.map((p) => p.platform));
  return (
    <Popup title="Side-by-side comparison" onClose={onClose} wide>
      {platforms.size > 1 && (
        <p className="notice small">These posts are from different platforms. Websites don't report views, so only dates, formats and topics can be compared between them.</p>
      )}
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
        Engagement rate = (likes + comments) ÷ views. "vs account's usual" compares each post with its own account, so accounts of different sizes can be compared.
        Views keep growing after publishing, so newer posts are at a disadvantage.
      </p>
    </Popup>
  );
}

export default function Explorer({ orgId, refreshKey, onNavigate }) {
  const [filters, setFilters] = useState(EMPTY);
  const [search, setSearch] = useState("");
  const [data, setData] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState([]);
  const [comparing, setComparing] = useState(false);

  // Update the saved state in place, so loaded pages and scroll position are kept.
  function onSaved(postId, savedIn, collection, delta) {
    setItems((cur) => cur.map((x) => (x.id === postId ? { ...x, saved_in: savedIn } : x)));
    setData((d) => {
      const list = d.facets.collections.some((c) => c.name === collection)
        ? d.facets.collections.map((c) => (c.name === collection ? { ...c, posts: c.posts + delta } : c))
        : [...d.facets.collections, { name: collection, posts: delta }];
      return { ...d, facets: { ...d.facets, collections: list } };
    });
  }

  // Wait for typing to pause before searching.
  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => (f.q === search ? f : { ...f, q: search })), 400);
    return () => clearTimeout(t);
  }, [search]);

  const params = (offset) => {
    const p = { ...filters, limit: PAGE, offset };
    if (p.since) p.since = new Date(p.since).toISOString();
    if (p.until) p.until = new Date(`${p.until}T23:59:59`).toISOString();
    return p;
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getContent(orgId, params(0))
      .then((d) => {
        if (cancelled) return;
        const safe = withDefaults(d);
        setData(safe);
        setItems(safe.items);
        setError("");
      })
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId, filters, refreshKey]);

  useEffect(() => setSelected([]), [orgId]);

  async function more() {
    setLoading(true);
    try {
      const d = await getContent(orgId, params(items.length));
      setItems((cur) => [...cur, ...withDefaults(d).items]);
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
  const niche = f?.my_topics || [];
  const nicheHint = !niche.length
    ? "No niche topics yet. Add topics in Workspace settings."
    : `${f.my_topics_source === "workspace" ? "Topics from Workspace settings" : "Topics your own posts cover"}: ${niche.join(", ")}`;
  const sorts = [["newest", "Newest first", true], ["views", "Most viewed", f?.has_views],
    ["engagement", "Highest engagement", f?.has_engagement], ["relative", "Best vs their usual", f?.has_relative]];

  return (
    <section className="panel">
      <PageHead
        title="Content Explorer"
        what="Every post collected from the accounts you track, with its public numbers and a link to the original."
        why={`"× usual" compares each post with its own account's typical views, so you can spot what worked for a channel of any size.`}
        next={`Tick up to ${MAX_COMPARE} posts to compare, save interesting ones to a collection, or turn one into an original brief.`}
      >
        <input className="search" placeholder="Search titles and tags…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search" />
      </PageHead>

      <div className="filters" role="group" aria-label="Filters">
        <select value={filters.collection} onChange={set("collection")} aria-label="Show">
          <option value="">All collected posts</option>
          {f?.collections.map((c) => <option key={c.name} value={c.name}>Saved: {c.name} ({c.posts})</option>)}
        </select>
        <select value={filters.account_id} onChange={set("account_id")} aria-label="Competitor">
          <option value="">All accounts</option>
          {f?.accounts.filter((a) => filters.include_ours || !a.is_us).map((a) => (
            <option key={a.id} value={a.id}>{a.name} ({PLATFORM_LABEL[a.platform] || a.platform})</option>
          ))}
        </select>
        <select value={filters.platform} onChange={set("platform")} aria-label="Platform">
          <option value="">All platforms</option>
          {ALL_PLATFORMS.map((p) => <option key={p} value={p}>{PLATFORM_LABEL[p]}</option>)}
        </select>
        {f?.formats.length > 1 && (
          <select value={filters.format} onChange={set("format")} aria-label="Format">
            <option value="">All formats</option>
            {f.formats.map((x) => <option key={x} value={x}>{FORMAT_LABEL[x] || x}</option>)}
          </select>
        )}
        <input list="topic-list" value={filters.topic} onChange={set("topic")} placeholder="Topic" aria-label="Topic" />
        <datalist id="topic-list">{f?.topics.map((t) => <option key={t} value={t} />)}</datalist>
        {f?.has_relative && (
          <select value={filters.performance} onChange={set("performance")} aria-label="Performance">
            <option value="">Any performance</option>
            <option value="outlier">2×+ account's usual</option>
            <option value="above">1.2×+ usual</option>
            <option value="usual">About usual</option>
            <option value="below">Below usual</option>
            <option value="unknown">No view data</option>
          </select>
        )}
        <label className="date-f">From <input type="date" value={filters.since} onChange={set("since")} /></label>
        <label className="date-f">To <input type="date" value={filters.until} onChange={set("until")} /></label>
        <select value={filters.sort} onChange={set("sort")} aria-label="Sort">
          {sorts.filter(([, , ok]) => ok).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <label className="check small" title={nicheHint}>
          <input type="checkbox" checked={filters.my_topics} onChange={set("my_topics")} /> My niche topics
        </label>
        <label className="check small"><input type="checkbox" checked={filters.include_ours} onChange={set("include_ours")} /> Include our posts</label>
        {active && <button className="btn ghost small-btn" onClick={() => { setFilters(EMPTY); setSearch(""); }}>Clear filters</button>}
      </div>

      {filters.my_topics && f && (
        <p className="notice small">
          {niche.length ? (
            <>
              Showing posts about {f.my_topics_source === "workspace" ? "the topics saved in Workspace settings" : "topics your own posts already cover"}:{" "}
              <b>{niche.slice(0, 8).join(", ")}</b>{niche.length > 8 ? ` and ${niche.length - 8} more` : ""}.
              {f.my_topics_source !== "workspace" && " To choose them yourself, add topics in the Workspace tab."}
            </>
          ) : (
            <>No niche topics found yet: your own posts don't share clear topics. Add topics in the Workspace tab to use this filter.</>
          )}
        </p>
      )}

      {selected.length > 0 && (
        <div className="compare-bar">
          <span>{selected.length} of {MAX_COMPARE} selected</span>
          <button className="btn primary small-btn" disabled={selected.length < 2} onClick={() => setComparing(true)}>Compare side by side</button>
          <button className="btn ghost small-btn" onClick={() => setSelected([])}>Clear</button>
        </div>
      )}

      {error ? (
        <Empty title="Content not available">{error}</Empty>
      ) : !data ? (
        <Loading what="Loading posts…" />
      ) : items.length === 0 ? (
        <Empty title={filters.collection ? `Nothing saved in "${filters.collection}" yet` : "No posts match"}>
          {filters.collection ? 'Use "Save…" on any post card to add it here.' : data.total === 0 && !active ? "Add competitors in Accounts and click Refresh." : "Try removing a filter."}
        </Empty>
      ) : (
        <>
          <p className="muted small">{data.total} post{data.total !== 1 ? "s" : ""}{loading && " · loading…"}</p>
          <div className="gallery">
            {items.map((p) => (
              <Card key={p.id} orgId={orgId} p={p} selected={selected.some((x) => x.id === p.id)} disabled={selected.length >= MAX_COMPARE}
                onToggle={() => toggle(p)} collections={f.collections} onChanged={onSaved} onNavigate={onNavigate} />
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
