import { useEffect, useState } from "react";
import { createOpportunity, fmtDate, getContent, getTopics, PLATFORM_LABEL, toIST } from "../api";
import { PostMini } from "../components/Evidence";
import PackagePopup from "../components/PackagePopup";
import Popup from "../components/Popup";

const STATUS_TONE = {
  not_covered_by_you: "bad", covered_less: "warn", covered: "good",
  limited_competitor_coverage: "neutral", no_posts_tracked: "neutral",
};
const FILTERS = [
  ["all", "All topics"], ["not_covered_by_you", "No posts from you"], ["covered_less", "You post less"],
  ["limited_competitor_coverage", "Few competitors"], ["covered", "Covered"], ["tracked", "My topics"],
];
const CONF_TONE = { high: "good", medium: "warn", low: "bad" };

function TopicEvidence({ orgId, topic, onClose }) {
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
        <div><span>Your posts</span><b>{topic.our_posts}</b></div>
        <div><span>Competitor posts</span><b>{topic.competitor_posts}</b></div>
        <div><span>Covered by</span><b>{topic.competitors.join(", ") || "–"}</b></div>
        <div><span>Audience questions</span><b>{topic.questions}</b></div>
        <div><span>Confidence</span><b>{topic.confidence}</b></div>
        <div><span>Latest post</span><b>{fmtDate(topic.latest)}</b></div>
      </div>
      {error && <p className="error-text">{error}</p>}
      {!posts && !error && <p className="muted">Loading posts…</p>}
      {posts && (posts.length === 0
        ? <p className="muted">No posts in the tracked data match this topic yet.</p>
        : <div className="post-mini-list">{posts.map((p) => <PostMini key={p.id} p={{ ...p, account: p.is_us ? `${p.account} (yours)` : p.account }} />)}</div>)}
      <p className="muted small">Matched by keywords in titles and tags. Posts about the same idea in different words won't show here.</p>
    </Popup>
  );
}

function StoryGaps({ gaps, windowHours }) {
  const [selected, setSelected] = useState(null);
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Same story, not covered by you</h2>
          <p className="muted">Specific stories that 2 or more competitors published in the last {windowHours >= 48 ? `${Math.round(windowHours / 24)} days` : `${windowHours} hours`} and you didn't (matched by headline similarity). Most useful for time-sensitive content.</p>
        </div>
      </div>
      {gaps.length === 0 ? (
        <div className="empty"><b>No missed stories right now</b><span>You covered every story that 2+ competitors covered in this period.</span></div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Priority</th><th>Story</th><th>Covered by</th><th>First published</th><th></th></tr></thead>
            <tbody>
              {gaps.map((g) => (
                <tr key={g.story_id}>
                  <td><span className={`pill ${g.priority === "P1" ? "p1" : "p2"}`}>{g.priority}</span></td>
                  <td className="story">
                    {g.title}
                    <div className="plats">{(g.platforms || []).map((p) => <span key={p} className={`plat ${p}`}>{PLATFORM_LABEL[p]}</span>)}</div>
                  </td>
                  <td><div className="chips">{g.covered_by.map((c) => <span className="chip static" key={c}>{c}</span>)}</div></td>
                  <td className="nowrap"><b>{g.first_by}</b><div className="muted small">{toIST(g.first_published_at)}</div></td>
                  <td><button className="btn primary small-btn" onClick={() => setSelected(g)}>Create Package</button></td>
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

export default function Gaps({ orgId, gaps, windowHours, config, recKeys, onNavigate, refreshKey }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [inspect, setInspect] = useState(null);
  const [msg, setMsg] = useState({});

  useEffect(() => {
    let cancelled = false;
    getTopics(orgId)
      .then((d) => !cancelled && (setData(d), setError("")))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [orgId, refreshKey]);

  async function brief(t) {
    const key = `topic_gap:${t.topic.toLowerCase()}`;
    try {
      await createOpportunity(orgId, key, "brief");
      setMsg((m) => ({ ...m, [t.topic]: "ok" }));
    } catch (e) {
      setMsg((m) => ({ ...m, [t.topic]: e.message }));
    }
  }

  const topics = (data?.topics || []).filter((t) =>
    (filter === "all" || (filter === "tracked" ? t.tracked : t.status === filter)) &&
    t.topic.toLowerCase().includes(search.toLowerCase())
  );
  const showStories = config?.time_sensitive || gaps.length > 0;

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Topic coverage map</h2>
            <p className="muted">
              Topics in your and your competitors' posts from {data ? `${fmtDate(data.period.from)} to ${fmtDate(data.period.to)}` : "the comparison period"}
              {data && ` (${data.your_posts_checked} of your posts, ${data.competitor_posts_checked} competitor posts)`}. {data?.method}
            </p>
          </div>
          <input className="search" placeholder="Search topics…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search topics" />
        </div>

        <div className="chips">
          {FILTERS.map(([id, label]) => (
            <button key={id} className={`chip ${filter === id ? "on" : ""}`} onClick={() => setFilter(id)}>{label}</button>
          ))}
        </div>
        {!config?.topics?.length && (
          <p className="notice small">
            Tip: add your own topics and keywords in <button className="link-btn" onClick={() => onNavigate("workspace")}>Workspace settings</button> so they're always tracked here.
          </p>
        )}

        {error ? (
          <div className="empty"><b>Topics not available</b><span>{error}</span></div>
        ) : !data ? (
          <div className="empty"><b>Loading topics…</b></div>
        ) : topics.length === 0 ? (
          <div className="empty"><b>No topics to show</b><span>{data.topics.length ? "Try another filter." : "Add accounts and click Refresh. Topics appear once 2+ accounts post about the same thing."}</span></div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Topic</th><th>Coverage in tracked data</th><th>You vs per competitor</th><th>Covered by</th><th title="Median of competitors' posts on this topic, each compared with its own account's usual views">Their typical performance</th><th>Questions</th><th>Confidence</th><th></th></tr>
              </thead>
              <tbody>
                {topics.map((t) => {
                  const max = Math.max(t.our_posts, t.per_competitor, 1);
                  const canBrief = recKeys.has(`topic_gap:${t.topic.toLowerCase()}`);
                  return (
                    <tr key={t.topic}>
                      <td className="nowrap"><b>{t.topic}</b>{t.tracked && <span className="pill neutral tiny">My topic</span>}</td>
                      <td><span className={`pill ${STATUS_TONE[t.status]}`}>{t.status_label}</span></td>
                      <td className="bars" aria-label={`You ${t.our_posts}, per competitor ${t.per_competitor}`}>
                        <div><span className="bar us" style={{ width: `${(t.our_posts / max) * 100}%` }} /><small>You {t.our_posts}</small></div>
                        <div><span className="bar them" style={{ width: `${(t.per_competitor / max) * 100}%` }} /><small>Them {t.per_competitor}</small></div>
                      </td>
                      <td className="small">{t.competitors.join(", ") || "–"}</td>
                      <td className="num">{t.median_relative != null ? `${t.median_relative}×` : "–"}{t.relative_sample ? <div className="muted small">{t.relative_sample} posts</div> : null}</td>
                      <td className="num">{t.questions || "–"}</td>
                      <td><span className={`pill ${CONF_TONE[t.confidence]}`}>{t.confidence}</span></td>
                      <td>
                        <div className="row-actions">
                          <button className="btn ghost small-btn" onClick={() => setInspect(t)}>Evidence</button>
                          {canBrief && (msg[t.topic] === "ok"
                            ? <button className="btn ghost small-btn" onClick={() => onNavigate("opportunities")}>Brief ready →</button>
                            : <button className="btn primary small-btn" onClick={() => brief(t)}>Create brief</button>)}
                        </div>
                        {msg[t.topic] && msg[t.topic] !== "ok" && <div className="error-text small">{msg[t.topic]}</div>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted small">
          "No posts from you" only means none of your collected posts matched these keywords in this period. It doesn't mean the topic is untapped:
          we only see the accounts you track and the latest posts each platform returns.
        </p>
      </section>

      {showStories && <StoryGaps gaps={gaps} windowHours={windowHours} />}
      {inspect && <TopicEvidence orgId={orgId} topic={inspect} onClose={() => setInspect(null)} />}
    </>
  );
}
