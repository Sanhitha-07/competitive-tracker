import { Fragment, useEffect, useMemo, useState } from "react";
import { fmtDate, getContent, getTopics, PLATFORM_LABEL, saveConfig, toIST } from "../api";
import { PostMini } from "../components/Evidence";
import PackagePopup from "../components/PackagePopup";
import Popup from "../components/Popup";
import { BriefButton, Empty, Loading, PageHead, Tip } from "../components/ui";

const STATUS_TONE = {
  not_covered_by_you: "bad", covered_less: "warn", covered_underperforming: "warn", covered: "good",
  limited_competitor_coverage: "neutral", no_posts_tracked: "neutral",
};
const FILTERS = [
  ["opportunity", "Potential opportunities"], ["not_covered_by_you", "Never covered by you"],
  ["covered_less", "You post less"], ["covered_underperforming", "Your posts underperform"],
  ["covered", "Covered"], ["tracked", "My topics"], ["all", "All topics"],
];
const PERIODS = [["", "Workspace period"], [7, "Last 7 days"], [14, "Last 14 days"], [30, "Last 30 days"], [90, "Last 90 days"]];
const CONF_TONE = { high: "good", medium: "warn", low: "bad" };

function TopicEvidence({ orgId, topic, onClose, onNavigate }) {
  const [posts, setPosts] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getContent(orgId, { topic: topic.topic, include_ours: true, sort: "relative", limit: 30 })
      .then((d) => setPosts(d.items))
      .catch((e) => setError(e.message));
  }, [orgId, topic.topic]);
  return (
    <Popup title={`Evidence: "${topic.topic}"`} onClose={onClose} wide>
      <div className="meta-grid">
        <div><span>Your posts</span><b>{topic.our_posts}{topic.our_median_relative !== null && ` (${topic.our_median_relative}× your usual)`}</b></div>
        <div><span>Competitor posts</span><b>{topic.competitor_posts}{topic.median_relative !== null && ` (${topic.median_relative}× their usual)`}</b></div>
        <div><span>Covered by</span><b>{topic.competitors.join(", ") || "–"}</b></div>
        <div><span>Audience questions</span><b>{topic.questions}</b></div>
        <div><span>Confidence</span><b>{topic.confidence}</b></div>
        <div><span>Latest post</span><b>{fmtDate(topic.latest)}</b></div>
      </div>
      <p className="plain"><b>Why:</b> {topic.reason}</p>
      {error && <p className="error-text">{error}</p>}
      {!posts && !error && <Loading what="Loading posts…" />}
      {posts && (posts.length === 0
        ? <p className="muted">No posts in the tracked data match this topic yet.</p>
        : <div className="post-mini-list">{posts.map((p) => <PostMini key={p.id} p={{ ...p, account: p.is_us ? `${p.account} (yours)` : p.account }} />)}</div>)}
      <p className="muted small">Matched by keywords in titles and tags. Posts about the same idea in different words won't show here: merge topics to join them.</p>
      {topic.competitor_posts > 0 && (
        <div className="popup-actions"><BriefButton orgId={orgId} source={{ topic: topic.topic }} onNavigate={onNavigate} /></div>
      )}
    </Popup>
  );
}

// Fix a wrongly classified topic: rename it, merge it into another topic, or exclude it.
function CorrectTopic({ topic, topics, rules, onSave, onClose }) {
  const [mode, setMode] = useState("rename");
  const [name, setName] = useState(topic.topic);
  const [into, setInto] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const term = topic.topic.toLowerCase();

  async function save() {
    const aliases = { ...rules.aliases };
    let excluded = [...rules.excluded];
    // A renamed topic keeps the terms that were already merged into it.
    const sources = [term, ...Object.entries(aliases).filter(([, v]) => v.toLowerCase() === term).map(([k]) => k)];
    if (mode === "exclude") {
      excluded = [...new Set([...excluded, term])];
    } else {
      const target = (mode === "rename" ? name : into).trim();
      if (!target) return setError(mode === "rename" ? "Enter a name." : "Choose a topic to merge into.");
      if (target.length > 60) return setError("Up to 60 characters.");
      sources.forEach((s) => { if (s !== target.toLowerCase()) aliases[s] = target; });
    }
    setBusy(true);
    try {
      await onSave({ aliases, excluded });
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Popup title={`Correct "${topic.topic}"`} onClose={onClose}>
      <div className="segmented" role="tablist">
        {[["rename", "Rename"], ["merge", "Merge into another topic"], ["exclude", "Not a topic"]].map(([id, label]) => (
          <button key={id} role="tab" aria-selected={mode === id} className={mode === id ? "on" : ""} onClick={() => setMode(id)}>{label}</button>
        ))}
      </div>
      {mode === "rename" && (
        <label className="field"><span>New name</span><input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} /></label>
      )}
      {mode === "merge" && (
        <label className="field">
          <span>Merge into</span>
          <input list="merge-targets" value={into} onChange={(e) => setInto(e.target.value)} placeholder="Type or pick a topic" />
          <datalist id="merge-targets">{topics.filter((t) => t.topic !== topic.topic).map((t) => <option key={t.topic} value={t.topic} />)}</datalist>
          <small className="muted">Posts about "{topic.topic}" will count under that topic, e.g. "whey" into "protein".</small>
        </label>
      )}
      {mode === "exclude" && (
        <p className="plain">"{topic.topic}" will be hidden everywhere in this workspace (coverage map, suggestions, Content DNA). Use this for names, brands or words that aren't topics.</p>
      )}
      {error && <p className="error-text">{error}</p>}
      <div className="popup-actions">
        <button className="btn ghost" onClick={onClose}>Cancel</button>
        <button className="btn primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save correction"}</button>
      </div>
    </Popup>
  );
}

function Corrections({ rules, onSave }) {
  const aliases = Object.entries(rules.aliases);
  if (!aliases.length && !rules.excluded.length) return null;
  const undoAlias = (k) => { const a = { ...rules.aliases }; delete a[k]; onSave({ ...rules, aliases: a }); };
  const undoExcl = (k) => onSave({ ...rules, excluded: rules.excluded.filter((x) => x !== k) });
  return (
    <details className="evidence">
      <summary>Your topic corrections ({aliases.length + rules.excluded.length})</summary>
      <div className="chips corrections">
        {aliases.map(([k, v]) => <span key={k} className="chip static">{k} → {v} <button className="chip-x" aria-label={`Undo ${k}`} onClick={() => undoAlias(k)}>×</button></span>)}
        {rules.excluded.map((k) => <span key={k} className="chip static">hidden: {k} <button className="chip-x" aria-label={`Show ${k} again`} onClick={() => undoExcl(k)}>×</button></span>)}
      </div>
    </details>
  );
}

function StoryGaps({ gaps, windowHours }) {
  const [selected, setSelected] = useState(null);
  return (
    <section className="panel">
      <PageHead title="Same story, not covered by you"
        what={`Specific stories that 2 or more competitors published in the last ${windowHours >= 48 ? `${Math.round(windowHours / 24)} days` : `${windowHours} hours`} and you didn't, matched by headline similarity. Most useful for time-sensitive content.`} />
      {gaps.length === 0 ? (
        <Empty title="No missed stories right now">You covered every story that 2+ competitors covered in this period.</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Priority</th><th>Story</th><th>Covered by</th><th>First published</th><th></th></tr></thead>
            <tbody>
              {gaps.map((g) => (
                <tr key={g.story_id}>
                  <td><span className={`pill ${g.priority === "P1" ? "p1" : "p2"}`} title={g.priority === "P1" ? "3+ competitors" : "2 competitors"}>{g.priority}</span></td>
                  <td className="story">
                    {g.title}
                    <div className="plats">{(g.platforms || []).map((p) => <span key={p} className={`plat ${p}`}>{PLATFORM_LABEL[p]}</span>)}</div>
                  </td>
                  <td><div className="chips">{g.covered_by.map((c) => <span className="chip static" key={c}>{c}</span>)}</div></td>
                  <td className="nowrap"><b>{g.first_by}</b><div className="muted small">{toIST(g.first_published_at)}</div></td>
                  <td><button className="btn primary small-btn" onClick={() => setSelected(g)}>Create package</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selected && <PackagePopup gap={selected} onClose={() => setSelected(null)} />}
    </section>
  );
}

function TopicRow({ t, child, open, related, onToggle, onInspect, onCorrect, orgId, onNavigate }) {
  const max = Math.max(t.our_posts, t.per_competitor, 1);
  return (
    <tr className={child ? "child-row" : ""}>
      <td>
        <div className="topic-cell">
          {child && <span className="muted" aria-hidden="true">↳</span>}
          <b>{t.topic}</b>
          {t.tracked && <span className="pill neutral tiny">My topic</span>}
          {t.renamed && <span className="pill neutral tiny" title="Renamed or merged by you">Corrected</span>}
        </div>
        {related > 0 && (
          <button className="link-btn small" onClick={onToggle} aria-expanded={open}>{open ? "Hide" : "Show"} {related} related</button>
        )}
      </td>
      <td>
        <span className={`pill ${STATUS_TONE[t.status]}`}>{t.status_label}</span>
        <div><span className={`pill tiny ${CONF_TONE[t.confidence]}`} title="Based on the number of posts and accounts">{t.confidence} confidence</span></div>
      </td>
      <td className="bars" aria-label={`You ${t.our_posts}, per competitor ${t.per_competitor}`}>
        <div><span className="bar us" style={{ width: `${(t.our_posts / max) * 100}%` }} /><small>You {t.our_posts}</small></div>
        <div><span className="bar them" style={{ width: `${(t.per_competitor / max) * 100}%` }} /><small>Them {t.per_competitor}</small></div>
      </td>
      <td className="num">
        {t.median_relative !== null ? `${t.median_relative}×` : "–"}
        {t.relative_sample ? <div className="muted tiny-text">{t.relative_sample} posts</div> : null}
      </td>
      <td className="small reason-cell">{t.reason}</td>
      <td>
        <div className="row-actions">
          <button className="btn ghost small-btn" onClick={() => onInspect(t)}>Evidence</button>
          {t.opportunity && <BriefButton orgId={orgId} source={{ topic: t.topic }} onNavigate={onNavigate} />}
          <button className="btn ghost small-btn" onClick={() => onCorrect(t)} title="Rename, merge or hide this topic">Correct</button>
        </div>
      </td>
    </tr>
  );
}

export default function Gaps({ orgId, gaps, windowHours, config, onNavigate, refreshKey, onConfigChanged }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("opportunity");
  const [search, setSearch] = useState("");
  const [days, setDays] = useState("");
  const [competitor, setCompetitor] = useState("");
  const [inspect, setInspect] = useState(null);
  const [correct, setCorrect] = useState(null);
  const [open, setOpen] = useState({});
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getTopics(orgId, { days, competitor_id: competitor })
      .then((d) => !cancelled && (setData(d), setError("")))
      .catch((e) => !cancelled && setError(e.message));
    return () => { cancelled = true; };
  }, [orgId, refreshKey, days, competitor, reload]);

  async function saveRules(rules) {
    await saveConfig(orgId, { topic_rules: rules });
    setReload((n) => n + 1);
    onConfigChanged?.();
  }

  const matches = (t) =>
    (filter === "all" || (filter === "tracked" ? t.tracked : filter === "opportunity" ? t.opportunity : t.status === filter)) &&
    t.topic.toLowerCase().includes(search.toLowerCase());
  // Group related topics under the topic with the most posts. A group shows when any member matches.
  const groups = useMemo(() => {
    const all = data?.topics || [];
    const byGroup = new Map();
    all.forEach((t) => {
      const key = t.group ?? t.topic; // older API versions send no groups: each topic stands alone
      if (!byGroup.has(key)) byGroup.set(key, []);
      byGroup.get(key).push(t);
    });
    return [...byGroup.values()]
      .map((members) => {
        const lead = members.find((m) => m.topic === (m.group ?? m.topic)) || members[0];
        return { lead, rest: members.filter((m) => m !== lead) };
      })
      .filter((g) => matches(g.lead) || g.rest.some(matches));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, filter, search]);
  const rules = { aliases: {}, excluded: [], ...(data?.rules || {}) };
  const showStories = config?.time_sensitive || gaps.length > 0;
  const counts = Object.fromEntries(FILTERS.map(([id]) => [id, (data?.topics || []).filter((t) =>
    id === "all" || (id === "tracked" ? t.tracked : id === "opportunity" ? t.opportunity : t.status === id)).length]));

  return (
    <>
      <section className="panel">
        <PageHead
          title="Coverage gaps"
          what={`Topics in your and your competitors' posts${data ? ` from ${fmtDate(data.period.from)} to ${fmtDate(data.period.to)} (${data.your_posts_checked} of your posts, ${data.competitor_posts_checked} competitor posts)` : ""}.`}
          why="Topics several competitors cover, and you don't (or your posts do poorly on), may be worth an original post."
          next='Open the evidence, then "Create brief". Fix any wrongly grouped topic with "Correct".'
        >
          <input className="search" placeholder="Search topics…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search topics" />
        </PageHead>

        <div className="filters">
          <select value={days} onChange={(e) => setDays(e.target.value)} aria-label="Period">
            {PERIODS.map(([d, l]) => <option key={l} value={d}>{l}</option>)}
          </select>
          <select value={competitor} onChange={(e) => setCompetitor(e.target.value)} aria-label="Competitor">
            <option value="">All competitors</option>
            {(data?.competitors || []).map((c) => <option key={c.id} value={c.id}>{c.name} ({PLATFORM_LABEL[c.platform]})</option>)}
          </select>
        </div>
        <div className="chips" role="tablist" aria-label="Filter topics">
          {FILTERS.filter(([id]) => ["opportunity", "all"].includes(id) || counts[id]).map(([id, label]) => (
            <button key={id} role="tab" aria-selected={filter === id} className={`chip ${filter === id ? "on" : ""}`} onClick={() => setFilter(id)}>
              {label} <span className="chip-count">{counts[id]}</span>
            </button>
          ))}
        </div>
        {!config?.topics?.length && (
          <p className="notice small">
            Tip: add your own topics in <button className="link-btn" onClick={() => onNavigate("workspace")}>Workspace settings</button> so
            they're always tracked and recognised as relevant.
          </p>
        )}
        {data && <Corrections rules={rules} onSave={saveRules} />}

        {error ? (
          <Empty title="Topics not available">{error}</Empty>
        ) : !data ? (
          <Loading what="Loading topics…" />
        ) : groups.length === 0 ? (
          <Empty title={filter === "opportunity" ? "No potential gaps right now" : "No topics to show"}>
            {data.topics.length ? "Try another filter or a longer period." : "Add accounts and click Refresh. Topics appear once 2+ accounts post about the same thing."}
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Topic</th><th>Coverage</th><th>Posts: you vs competitors</th>
                  <th className="num">Their results <Tip text="Median of competitors' posts on this topic, each compared with its own account's usual views." /></th>
                  <th>Why</th><th></th></tr>
              </thead>
              <tbody>
                {groups.map(({ lead, rest }) => (
                  <Fragment key={lead.topic}>
                    <TopicRow t={lead} related={rest.length} open={open[lead.topic]} onToggle={() => setOpen((o) => ({ ...o, [lead.topic]: !o[lead.topic] }))}
                      onInspect={setInspect} onCorrect={setCorrect} orgId={orgId} onNavigate={onNavigate} />
                    {open[lead.topic] && rest.map((t) => (
                      <TopicRow key={t.topic} t={t} child onInspect={setInspect} onCorrect={setCorrect} orgId={orgId} onNavigate={onNavigate} />
                    ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted small">
          "Never covered by you" only means none of your collected posts matched these keywords in this period. We only see the accounts
          you track and the latest posts each platform returns. {data?.method}
        </p>
      </section>

      {showStories && <StoryGaps gaps={gaps} windowHours={windowHours} />}
      {inspect && <TopicEvidence orgId={orgId} topic={inspect} onClose={() => setInspect(null)} onNavigate={onNavigate} />}
      {correct && data && <CorrectTopic topic={correct} topics={data.topics} rules={rules} onSave={saveRules} onClose={() => setCorrect(null)} />}
    </>
  );
}
