import { useEffect, useState } from "react";
import { compact, duration, fmtDate, fmtTime, FORMAT_LABEL, getHistory, PLATFORM_LABEL, toIST, tzLabel } from "../api";

const METRICS = [
  { key: "per_week", def: "per_week", label: "Videos / week", fmt: (v) => v, higherIsBetter: true },
  { key: "median_views", def: "median_views", label: "Typical views", fmt: compact, higherIsBetter: true },
  { key: "engagement_rate", def: "engagement_rate", label: "Engagement", fmt: (v) => `${v}%`, higherIsBetter: true },
  { key: "avg_length_seconds", def: "duration", label: "Avg length", fmt: duration },
  { key: "shorts_pct", def: null, label: "Shorts", fmt: (v) => `${v}%` },
];
const FORMATS = ["short", "video", "long", "live"];

function Diff({ us, market, higherIsBetter }) {
  if (us === undefined || market === undefined || !market) return null;
  const pct = Math.round(((us - market) / market) * 100);
  if (pct === 0) return <span className="diff">level</span>;
  const tone = higherIsBetter === undefined ? "" : (pct > 0) === higherIsBetter ? "good" : "bad";
  return <span className={`diff ${tone}`}>{pct > 0 ? "▲" : "▼"} {Math.abs(pct)}%</span>;
}

function FormatTable({ accounts }) {
  const used = FORMATS.filter((f) => accounts.some((a) => a.stats?.formats?.[f]));
  if (used.length < 1) return null;
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>By content format (YouTube)</h2>
          <p className="muted">Number of videos and typical (median) views per format, last 30 days. Shorts are approximate: the API doesn't mark Shorts, so videos of 60s or less are counted.</p>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Channel</th>{used.map((f) => <th key={f}>{FORMAT_LABEL[f]}</th>)}</tr></thead>
          <tbody>
            {accounts.filter((a) => a.stats).map((a) => (
              <tr key={a.id} className={a.is_us ? "us-row" : ""}>
                <td className="nowrap"><b>{a.name}</b></td>
                {used.map((f) => {
                  const s = a.stats.formats?.[f];
                  return (
                    <td key={f} className="num">
                      {s ? <>{compact(s.median_views)} <span className="muted small">· {s.videos} video{s.videos !== 1 ? "s" : ""} · {s.engagement_rate}%</span></> : <span className="muted">–</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function OtherPlatforms({ other }) {
  const entries = Object.entries(other || {});
  if (!entries.length) return null;
  return entries.map(([platform, rows]) => (
    <section className="panel" key={platform}>
      <div className="panel-head">
        <div>
          <h2>{PLATFORM_LABEL[platform] || platform}: posting activity</h2>
          <p className="muted">This platform doesn't share views or engagement, so only posting activity is compared (last 30 days).</p>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Account</th><th>Posts</th><th>Per week</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={r.is_us ? "us-row" : ""}>
                <td><b>{r.name}</b></td><td className="num">{r.posts}</td><td className="num">{r.per_week}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  ));
}

function History({ orgId, refreshKey }) {
  const [h, setH] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getHistory(orgId, 90).then(setH).catch((e) => setError(e.message));
  }, [orgId, refreshKey]);
  if (error) return <section className="panel"><p className="error-text">History not available: {error}</p></section>;
  if (!h) return null;
  const weeks = [...new Set(h.accounts.flatMap((a) => a.weekly.map((w) => w.week)))].sort().slice(-8);
  const withViews = h.accounts.filter((a) => a.weekly.some((w) => w.median_views != null));
  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Over time</h2>
            <p className="muted">Public numbers saved at each Refresh, plus weekly figures from the posts we've collected.</p>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Account</th><th>Audience change</th><th>Baseline (usual views)</th></tr></thead>
            <tbody>
              {h.accounts.map((a) => (
                <tr key={a.id} className={a.is_us ? "us-row" : ""}>
                  <td className="nowrap"><b>{a.name}</b> <span className={`plat ${a.platform}`}>{PLATFORM_LABEL[a.platform] || a.platform}</span></td>
                  <td className="small">
                    {a.audience_growth
                      ? <>{a.audience_growth.change >= 0 ? "+" : ""}{a.audience_growth.change.toLocaleString("en-IN")} ({compact(a.audience_growth.from)} → {compact(a.audience_growth.to)}) since {fmtDate(a.audience_growth.since)}</>
                      : <span className="muted">Needs 2+ refreshes</span>}
                  </td>
                  <td className="small">{a.baseline ? `${compact(a.baseline.median_views)} (median of ${a.baseline.posts} posts)` : <span className="muted">Not enough posts with views</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {withViews.length > 0 && weeks.length > 1 && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Weekly median views</th>{weeks.map((w) => <th key={w} className="nowrap">wk of {fmtDate(w)}</th>)}</tr></thead>
              <tbody>
                {withViews.map((a) => (
                  <tr key={a.id} className={a.is_us ? "us-row" : ""}>
                    <td className="nowrap"><b>{a.name}</b></td>
                    {weeks.map((w) => {
                      const x = a.weekly.find((y) => y.week === w);
                      return <td key={w} className="num">{x?.median_views != null ? <>{compact(x.median_views)} <span className="muted small">({x.posts})</span></> : <span className="muted">–</span>}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <ul className="limits small">{h.notes.map((n) => <li key={n}>{n}</li>)}</ul>
      </section>

      {h.our_recent_vs_baseline.length > 0 && (
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Your recent posts vs your usual</h2>
              <p className="muted">Each post's views ÷ your median views (posts 48h+ old, last 90 days). Posts under 48 hours old aren't compared yet.</p>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Post</th><th>Published</th><th>Views</th><th>vs your usual</th></tr></thead>
              <tbody>
                {h.our_recent_vs_baseline.map((p) => (
                  <tr key={p.id}>
                    <td className="story"><a href={p.link} target="_blank" rel="noreferrer">{p.title}</a></td>
                    <td className="nowrap small">{fmtTime(p.published_at)}</td>
                    <td className="num">{compact(p.views)}</td>
                    <td className="num">{p.relative != null ? <span className={p.relative >= 1.2 ? "good-text" : p.relative < 0.8 ? "bad-text" : ""}>{p.relative}×</span> : <span className="muted">–</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}

export default function Performance({ orgId, perf, definitions, refreshKey }) {
  const hasYouTube = perf && perf.accounts.length > 0;
  if (!perf || (!hasYouTube && !Object.keys(perf.other_platforms || {}).length)) {
    return (
      <section className="panel">
        <div className="empty">
          <b>No accounts to compare yet</b>
          <span>Add your account and competitors' accounts in the Accounts tab, then click Refresh.</span>
        </div>
      </section>
    );
  }
  const { us, market } = perf;

  return (
    <>
      {hasYouTube && (
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>You vs competitors on YouTube</h2>
              <p className="muted">
                Videos from the last {perf.days} days. "Competitors" = the average of {market?.accounts ?? 0} competitor channel{market?.accounts === 1 ? "" : "s"}, each counted once.
                Views and engagement depend heavily on channel size, so also check "vs usual" in Content Explorer.
              </p>
            </div>
          </div>

          {us && market ? (
            <div className="compare">
              {METRICS.map((m) => (
                <div className="compare-card" key={m.key}>
                  <span className="card-label">{m.label}</span>
                  <div className="compare-row">
                    <div><small>You ({us.videos})</small><b>{m.fmt(us[m.key])}</b></div>
                    <div><small>Competitors ({market.total_videos})</small><b>{m.fmt(market[m.key])}</b></div>
                  </div>
                  <Diff us={us[m.key]} market={market[m.key]} higherIsBetter={m.higherIsBetter} />
                  {m.def && definitions?.[m.def] && <small className="muted def">{definitions[m.def]}</small>}
                  {m.key === "shorts_pct" && <small className="muted def">Share of videos of 60s or less (approximate: the API doesn't mark Shorts).</small>}
                </div>
              ))}
            </div>
          ) : (
            <p className="notice">{us ? "No competitor posted in this period." : "Your channel has no videos in this period, or isn't marked as Ours."}</p>
          )}

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Channel</th><th title={definitions?.subscribers}>Subscribers</th><th>Videos</th><th>Per week</th><th title={definitions?.median_views}>Typical views</th>
                  <th>Avg views</th><th title={definitions?.engagement_rate}>Engagement</th><th>Avg length</th><th>Shorts</th><th>Best slot ({tzLabel()})</th>
                </tr>
              </thead>
              <tbody>
                {perf.accounts.map((a) => (
                  <tr key={a.id} className={a.is_us ? "us-row" : ""}>
                    <td className="nowrap"><b>{a.name}</b></td>
                    <td className="num">{compact(a.subscribers)}</td>
                    {a.stats ? (
                      <>
                        <td className="num">{a.stats.videos}</td>
                        <td className="num">{a.stats.per_week}</td>
                        <td className="num">{compact(a.stats.median_views)}</td>
                        <td className="num">{compact(a.stats.avg_views)}</td>
                        <td className="num">{a.stats.engagement_rate}%</td>
                        <td className="num">{duration(a.stats.avg_length_seconds)}</td>
                        <td className="num">{a.stats.shorts_pct}%</td>
                        <td className="nowrap small">{a.stats.best_time ? `${a.stats.best_time} (${a.stats.best_time_sample})` : "–"}</td>
                      </>
                    ) : (
                      <td colSpan={8} className="muted small">No videos in the last {perf.days} days</td>
                    )}
                  </tr>
                ))}
                {market && (
                  <tr className="market-row">
                    <td><b>Competitor average</b></td>
                    <td></td>
                    <td className="num">{market.videos}</td>
                    <td className="num">{market.per_week}</td>
                    <td className="num">{compact(market.median_views)}</td>
                    <td className="num">{compact(market.avg_views)}</td>
                    <td className="num">{market.engagement_rate}%</td>
                    <td className="num">{duration(market.avg_length_seconds)}</td>
                    <td className="num">{market.shorts_pct}%</td>
                    <td className="nowrap small">{market.best_time || "–"}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <p className="muted small">Best slot = the time of day whose videos have the highest median views (number of videos in brackets). Treat small numbers as a hint, not a rule.</p>
        </section>
      )}

      {hasYouTube && <FormatTable accounts={perf.accounts} />}
      <OtherPlatforms other={perf.other_platforms} />
      <History orgId={orgId} refreshKey={refreshKey} />

      {perf.top_competitor_videos.length > 0 && (
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Competitors' top videos</h2>
              <p className="muted">Their most-watched videos in the last {perf.days} days. Learn from the topic, title and format. Don't copy.</p>
            </div>
          </div>
          <ol className="top-list">
            {perf.top_competitor_videos.map((v) => (
              <li key={v.link}>
                <a href={v.link} target="_blank" rel="noreferrer">{v.title}</a>
                <span className="muted small">{v.account} · {compact(v.views)} views · {duration(v.length_seconds)} · {toIST(v.published_at)}</span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </>
  );
}
