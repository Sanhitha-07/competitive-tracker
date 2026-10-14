import { useEffect, useState } from "react";
import {
  ago, ALL_PLATFORMS, compact, duration, fmtDate, fmtTime, FORMAT_LABEL, getDashboard, num, NOT_CONFIGURED_TEXT, PLATFORM_LABEL, ratio,
  ratioTone, tzLabel,
} from "../api";
import PlatformIcon from "../components/PlatformIcon";
import { PostMini } from "../components/Evidence";
import { Empty, Loading, PageHead, Tip } from "../components/ui";

const PERIODS = [[7, "Last 7 days"], [30, "Last 30 days"], [90, "Last 90 days"], [180, "Last 6 months"], [365, "Last 12 months"]];
const EMPTY = { days: 90, competitor_id: "", platform: "", format: "", topic: "" };
const METRIC_LABEL = { views: "Views", likes: "Likes", comments: "Comments", shares: "Shares" };
const METRIC_TIP = {
  x: { views: "Views X shows on the post (impressions). Not comparable with YouTube views.", shares: "Reposts." },
  facebook: { likes: "All reactions (like, love, etc.).", shares: "Shares." },
  instagram: { likes: "Missing when the account hides like counts." },
};

function value(m, v) {
  if (v === null || v === undefined) return "Not available";
  if (m.format === "percent") return `${v}%`;
  if (m.format === "compact") return compact(v);
  return v.toLocaleString("en-IN");
}

function SummaryCards({ metrics }) {
  return (
    <div className="dash-cards">
      {metrics.map((m) => (
        <div className="card" key={m.key}>
          <span className="card-label">{m.label} <Tip text={`${m.definition} Source: ${m.source}.`} /></span>
          <span className={`card-value ${m.ours === null ? "na" : ""}`}>{value(m, m.ours)}</span>
          {m.theirs !== null && m.theirs !== undefined && <span className="card-hint">Competitors: <b>{value(m, m.theirs)}</b></span>}
          {m.note && <span className="card-hint">{m.note}</span>}
          {m.sample_ours !== null && m.sample_theirs !== null && m.sample_theirs !== undefined && (
            <span className="card-hint">{m.sample_ours} vs {m.sample_theirs} posts</span>
          )}
        </div>
      ))}
    </div>
  );
}

function Insights({ items, onNavigate }) {
  if (!items.length) {
    return <p className="muted">No finding has enough evidence in this view yet. Insights need at least {3} posts on each side of a comparison.</p>;
  }
  return (
    <div className="insights">
      {items.map((i) => (
        <article key={i.id} className={`insight ${i.tone}`}>
          <b>{i.title}</b>
          <p>{i.detail}</p>
          <p className="muted small"><b>Why it matters:</b> {i.why}</p>
          <p className="muted small">{i.sample} {i.limitation}</p>
          {i.evidence?.length > 0 && (
            <details className="evidence">
              <summary>Supporting posts ({i.evidence.length})</summary>
              <div className="post-mini-list">{i.evidence.map((p) => <PostMini key={p.id} p={p} />)}</div>
            </details>
          )}
          {i.action && <div><button className="btn ghost small-btn" onClick={() => onNavigate(i.action.tab)}>{i.action.label} →</button></div>}
        </article>
      ))}
    </div>
  );
}

function RelCell({ r, published }) {
  if (r !== null && r !== undefined) return <span className={ratioTone(r)}>{r}×</span>;
  const tooNew = Date.now() - new Date(published).getTime() < 48 * 3600 * 1000;
  return <span className="muted small">{tooNew ? "Too new (under 48h)" : "Not enough history"}</span>;
}

function YouTubeSection({ yt, onNavigate }) {
  const base = yt.channels.filter((c) => c.baseline);
  return (
    <section className="panel">
      <PageHead
        title="YouTube performance"
        what={`Your YouTube videos in this view (${yt.total}). "vs your usual" = the video's views ÷ your channel's typical (median) views${base.length ? ` of ${base.map((c) => `${compact(c.baseline.median_views)} for ${c.name}`).join(", ")}` : ""}.`}
      />
      {!yt.connected ? (
        <Empty title="No YouTube channel of yours is connected">
          <button className="link-btn" onClick={() => onNavigate("accounts")}>Add your channel in Accounts</button> and tick "Ours".
        </Empty>
      ) : yt.items.length === 0 ? (
        <Empty title="No videos in this view">Try a longer period or remove a filter.</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Video</th><th>Channel</th><th>Published</th><th className="num">Views</th><th className="num">Likes</th><th className="num">Comments</th>
                <th className="num">vs your usual <Tip text="Views ÷ your channel's median views (videos 48h+ old, last 90 days). 2× = twice your usual." /></th></tr>
            </thead>
            <tbody>
              {yt.items.map((p) => (
                <tr key={p.id}>
                  <td className="story">
                    <a className="title-cell" href={p.link} target="_blank" rel="noreferrer">
                      {p.thumbnail ? <img src={p.thumbnail} alt="" loading="lazy" /> : <span className="thumb-ph">{FORMAT_LABEL[p.format] || "Video"}</span>}
                      <span>{p.title}</span>
                    </a>
                  </td>
                  <td className="small">{p.account}</td>
                  <td className="nowrap small">{fmtDate(p.published_at)}</td>
                  <td className="num">{num(p.views)}{p.metrics_updated_at && <div className="muted tiny-text">as of {fmtTime(p.metrics_updated_at)}</div>}</td>
                  <td className="num">{p.likes === null ? <span className="muted small" title="The creator hides the like count">Hidden</span> : compact(p.likes)}</td>
                  <td className="num">{p.comments === null ? <span className="muted small">Not available</span> : compact(p.comments)}</td>
                  <td className="num"><RelCell r={p.relative} published={p.published_at} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {yt.total > yt.items.length && <p className="muted small">Showing the latest {yt.items.length} of {yt.total}. See all in Content Explorer (tick "Include our posts").</p>}
    </section>
  );
}

// Instagram, Facebook or X: our posts, with only the metrics that platform reports.
function SocialSection({ s, onNavigate }) {
  const showRel = s.metrics.includes("views");
  return (
    <section className="panel">
      <PageHead
        title={<span className="title-with-icon"><PlatformIcon platform={s.platform} />{s.label} performance</span>}
        what={`Your ${s.label} posts in this view (${s.total}). ${s.label} reports: ${s.metrics.map((m) => METRIC_LABEL[m].toLowerCase()).join(", ")}.`}
      />
      {!s.configured ? (
        <Empty title={`${s.label} isn't configured`}>
          {NOT_CONFIGURED_TEXT}
        </Empty>
      ) : !s.connected ? (
        <Empty title={`No ${s.label} account of yours yet`}>
          <button className="link-btn" onClick={() => onNavigate("accounts")}>Connect {s.label} and add your account in Accounts</button>, ticking "Ours".
        </Empty>
      ) : s.items.length === 0 ? (
        <Empty title="No posts in this view">Click Refresh to collect posts, or try a longer period.</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Post</th><th>Account</th><th>Published</th>
                {s.metrics.map((m) => <th key={m} className="num">{METRIC_LABEL[m]} {METRIC_TIP[s.platform]?.[m] && <Tip text={METRIC_TIP[s.platform][m]} />}</th>)}
                {showRel && <th className="num">vs your usual <Tip text="Views ÷ your account's median views (posts 48h+ old, last 90 days)." /></th>}</tr>
            </thead>
            <tbody>
              {s.items.map((p) => (
                <tr key={p.id}>
                  <td className="story">
                    <a className="title-cell" href={p.link} target="_blank" rel="noreferrer">
                      {p.thumbnail ? <img src={p.thumbnail} alt="" loading="lazy" /> : <span className="thumb-ph">{FORMAT_LABEL[p.format] || "Post"}</span>}
                      <span>{p.title}</span>
                    </a>
                  </td>
                  <td className="small">{p.account}</td>
                  <td className="nowrap small">{fmtDate(p.published_at)}</td>
                  {s.metrics.map((m) => <td key={m} className="num">{p[m] === null || p[m] === undefined ? <span className="muted small">Not available</span> : compact(p[m])}</td>)}
                  {showRel && <td className="num"><RelCell r={p.relative} published={p.published_at} /></td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function SocialSections({ social, onNavigate }) {
  // Platforms with nothing to show (not set up, no accounts) collapse into one line instead of empty panels.
  const shown = social.filter((s) => s.configured || s.connected || s.competitors > 0);
  const hidden = social.filter((s) => !shown.includes(s));
  return (
    <>
      {shown.map((s) => <SocialSection key={s.platform} s={s} onNavigate={onNavigate} />)}
      {hidden.length > 0 && (
        <p className="muted small social-note">
          {hidden.map((s) => s.label).join(", ")}: {NOT_CONFIGURED_TEXT}
        </p>
      )}
    </>
  );
}

function WebsiteSection({ web, onNavigate }) {
  return (
    <section className="panel">
      <PageHead title="Website / blog performance" what={`Your website or blog articles in this view (${web.total}), from your RSS feed.`} />
      {!web.connected ? (
        <Empty title="No website or blog of yours is connected">
          <button className="link-btn" onClick={() => onNavigate("accounts")}>Add your RSS feed in Accounts</button> and tick "Ours".
        </Empty>
      ) : (
        <>
          <p className="notice small">{web.metrics_note}</p>
          {web.items.length === 0 ? (
            <Empty title="No articles in this view">Try a longer period or remove a filter.</Empty>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Article</th><th>Website</th><th>Published</th><th>Page views</th></tr></thead>
                <tbody>
                  {web.items.map((p) => (
                    <tr key={p.id}>
                      <td className="story"><a href={p.link} target="_blank" rel="noreferrer">{p.title}</a></td>
                      <td className="small">{p.account}</td>
                      <td className="nowrap small">{fmtTime(p.published_at)}</td>
                      <td className="muted small">Not available</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function FormatTopicTables({ formats, topics }) {
  const cell = (s) => (!s || !s.posts ? <span className="muted">–</span> : (
    <>{s.posts} posts{s.median_relative !== null && <> · <span className={ratioTone(s.median_relative)}>{s.median_relative}×</span></>}
      {!s.enough && s.posts > 0 && <div className="muted tiny-text">{s.sample < 3 ? "Too few with views to judge" : ""}</div>}</>
  ));
  return (
    <div className="two-col">
      <section className="panel">
        <PageHead title="By format" what="How each format does against each account's own usual views (median, with number of posts)." />
        {formats.length === 0 ? <p className="muted">No posts in this view.</p> : (
          <div className="table-wrap">
            <table className="compact-table">
              <thead><tr><th>Format</th><th>You</th><th>Competitors</th></tr></thead>
              <tbody>
                {formats.map((f) => (
                  <tr key={f.format}><td><b>{FORMAT_LABEL[f.format] || f.format}</b></td><td className="small">{cell(f.ours)}</td><td className="small">{cell(f.theirs)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted small">Shorts are approximate: YouTube's API doesn't mark Shorts, so videos of 60s or less are counted.</p>
      </section>
      <section className="panel">
        <PageHead title="By topic" what="Your topics with 2+ posts: how they do against your usual views." />
        {topics.length === 0 ? <p className="muted">Not enough posts on shared topics in this view.</p> : (
          <div className="table-wrap">
            <table className="compact-table">
              <thead><tr><th>Topic</th><th>You</th><th>Competitors</th></tr></thead>
              <tbody>
                {topics.map((t) => (
                  <tr key={t.topic}>
                    <td><b>{t.topic}</b></td>
                    <td className="small">{t.our_posts} posts{t.our_median_relative !== null && <> · <span className={ratioTone(t.our_median_relative)}>{t.our_median_relative}×</span></>}
                      {t.our_posts > 0 && !t.enough && <div className="muted tiny-text">Too few to judge</div>}</td>
                    <td className="small">{t.competitor_posts} posts{t.competitor_median_relative !== null && <> · {ratio(t.competitor_median_relative)}</>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function ChannelComparison({ perf }) {
  if (!perf?.accounts?.length) return null;
  const { market } = perf;
  return (
    <details className="panel details-panel">
      <summary><b>Channel-by-channel comparison (YouTube)</b> <span className="muted small">raw numbers per channel; big channels get more views</span></summary>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Channel</th><th className="num">Subscribers</th><th className="num">Videos</th><th className="num">Per week</th><th className="num">Typical views</th>
              <th className="num">Engagement</th><th className="num">Avg length</th><th className="num">Shorts</th><th>Best slot ({tzLabel()})</th></tr>
          </thead>
          <tbody>
            {perf.accounts.map((a) => (
              <tr key={a.id} className={a.is_us ? "us-row" : ""}>
                <td className="nowrap"><b>{a.name}</b></td>
                <td className="num">{num(a.subscribers)}</td>
                {a.stats ? (
                  <>
                    <td className="num">{a.stats.videos}</td>
                    <td className="num">{a.stats.per_week}</td>
                    <td className="num">{num(a.stats.median_views)}</td>
                    <td className="num">{a.stats.engagement_rate === null ? "Not available" : `${a.stats.engagement_rate}%`}</td>
                    <td className="num">{a.stats.avg_length_seconds === null ? "–" : duration(a.stats.avg_length_seconds)}</td>
                    <td className="num">{a.stats.shorts_pct === null ? "–" : `${a.stats.shorts_pct}%`}</td>
                    <td className="nowrap small">{a.stats.best_time ? `${a.stats.best_time} (${a.stats.best_time_sample})` : "–"}</td>
                  </>
                ) : <td colSpan={7} className="muted small">No videos in this period</td>}
              </tr>
            ))}
            {market && (
              <tr className="market-row">
                <td><b>Competitor average</b></td><td></td>
                <td className="num">{market.videos ?? "–"}</td><td className="num">{market.per_week ?? "–"}</td>
                <td className="num">{num(market.median_views)}</td>
                <td className="num">{market.engagement_rate === null ? "Not available" : `${market.engagement_rate}%`}</td>
                <td className="num">{market.avg_length_seconds === null ? "–" : duration(market.avg_length_seconds)}</td>
                <td className="num">{market.shorts_pct === null ? "–" : `${market.shorts_pct}%`}</td>
                <td className="nowrap small">{market.best_time || "–"}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="muted small">Best slot = the time of day whose videos have the highest median views (number of videos in brackets). Treat small numbers as a hint, not a rule.</p>
    </details>
  );
}

export default function Performance({ orgId, refreshKey, onNavigate }) {
  const [filters, setFilters] = useState(EMPTY);
  const [topicText, setTopicText] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => (f.topic === topicText ? f : { ...f, topic: topicText })), 400);
    return () => clearTimeout(t);
  }, [topicText]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getDashboard(orgId, filters)
      .then((d) => !cancelled && (setData(d), setError("")))
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [orgId, filters, refreshKey]);

  const set = (k) => (e) => setFilters({ ...filters, [k]: e.target.value });
  const active = filters.competitor_id || filters.platform || filters.format || filters.topic || filters.days !== EMPTY.days;

  if (error) return <section className="panel"><Empty title="Performance not available">{error}</Empty></section>;
  if (!data) return <section className="panel"><Loading what="Loading performance…" /></section>;
  const f = data.facets;
  const platform = filters.platform;
  const show = (p) => !platform || platform === p; // with a platform filter, only that platform's sections
  const hasAccounts = (f.platforms || []).includes(platform);
  const noViews = ["instagram", "facebook", "rss"].includes(platform); // these platforms report no view counts

  return (
    <>
      <section className="panel">
        <PageHead
          title="Performance"
          what={`Your content compared with competitors from ${fmtDate(data.period.from)} to ${fmtDate(data.period.to)}. Data last refreshed ${ago(data.freshness.last_refresh)}.`}
          why="Comparing each account with its own usual results shows what really works, whatever the channel size."
          next="Check the insights, then turn a strong topic or format into an experiment in Opportunities."
        />
        <div className="filters" role="group" aria-label="Filters">
          <select value={filters.days} onChange={(e) => setFilters({ ...filters, days: Number(e.target.value) })} aria-label="Period">
            {PERIODS.map(([d, l]) => <option key={d} value={d}>{l}</option>)}
          </select>
          <select value={filters.competitor_id} onChange={set("competitor_id")} aria-label="Competitor">
            <option value="">All competitors</option>
            {f.competitors.map((c) => <option key={c.id} value={c.id}>{c.name} ({PLATFORM_LABEL[c.platform] || c.platform})</option>)}
          </select>
          <select value={filters.platform} onChange={set("platform")} aria-label="Platform">
            <option value="">All platforms</option>
            {ALL_PLATFORMS.map((p) => <option key={p} value={p}>{PLATFORM_LABEL[p]}</option>)}
          </select>
          {f.formats.length > 1 && (
            <select value={filters.format} onChange={set("format")} aria-label="Format">
              <option value="">All formats</option>
              {f.formats.map((x) => <option key={x} value={x}>{FORMAT_LABEL[x] || x}</option>)}
            </select>
          )}
          <input list="dash-topics" value={topicText} onChange={(e) => setTopicText(e.target.value)} placeholder="Topic" aria-label="Topic" />
          <datalist id="dash-topics">{f.topics.map((t) => <option key={t} value={t} />)}</datalist>
          {active && <button className="btn ghost small-btn" onClick={() => { setFilters(EMPTY); setTopicText(""); }}>Clear filters</button>}
          {loading && <span className="muted small">Updating…</span>}
        </div>
        {platform && !hasAccounts && (
          <p className="notice small">
            No {PLATFORM_LABEL[platform]} accounts in this workspace yet, so there's nothing to show for it.{" "}
            <button className="link-btn" onClick={() => onNavigate("accounts")}>Add accounts</button>
          </p>
        )}
        <SummaryCards metrics={data.summary} />
      </section>

      <section className="panel">
        <PageHead title="Quick insights" what="Findings with evidence behind them." />
        <Insights items={data.insights} onNavigate={onNavigate} />
      </section>

      <div className="two-col">
        <section className="panel">
          <PageHead title="Your strongest posts" what="Ranked by views compared with your usual, not raw views." />
          {data.top_posts.length ? (
            <div className="post-mini-list single">{data.top_posts.map((p) => <PostMini key={p.id} p={p} />)}</div>
          ) : (
            <p className="muted">{noViews ? `${PLATFORM_LABEL[platform]} doesn't report views, so posts can't be ranked against your usual.`
              : data.has_baseline ? "No posts of yours with view data in this view."
              : "Needs 5+ of your posts with views, at least 48 hours old (last 90 days), before 'vs usual' can be calculated."}</p>
          )}
        </section>
        <section className="panel">
          <PageHead title="Competitor standouts" what="Competitor posts at 1.5× or more of their own usual views." />
          {data.competitor_standouts.length ? (
            <div className="post-mini-list single">{data.competitor_standouts.map((p) => <PostMini key={p.id} p={p} />)}</div>
          ) : <p className="muted">{noViews ? `${PLATFORM_LABEL[platform]} doesn't report views, so standouts can't be found.` : "None in this view."}</p>}
        </section>
      </div>

      <FormatTopicTables formats={data.formats} topics={data.topics} />
      {show("youtube") && <YouTubeSection yt={data.youtube} onNavigate={onNavigate} />}
      {show("rss") && <WebsiteSection web={data.website} onNavigate={onNavigate} />}
      {data.social && <SocialSections social={data.social.filter((x) => show(x.platform))} onNavigate={onNavigate} />}
      {show("youtube") && <ChannelComparison perf={data.comparison} />}
    </>
  );
}
