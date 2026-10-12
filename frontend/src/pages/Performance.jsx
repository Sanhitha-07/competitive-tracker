import { compact, duration, toIST } from "../api";

const METRICS = [
  { key: "per_week", label: "Videos / week", fmt: (v) => v, higherIsBetter: true },
  { key: "median_views", label: "Typical views", fmt: compact, higherIsBetter: true },
  { key: "engagement_rate", label: "Engagement", fmt: (v) => `${v}%`, higherIsBetter: true },
  { key: "avg_length_seconds", label: "Avg length", fmt: duration },
  { key: "shorts_pct", label: "Shorts", fmt: (v) => `${v}%` },
];

function Diff({ us, market, higherIsBetter }) {
  if (us === undefined || market === undefined || !market) return null;
  const pct = Math.round(((us - market) / market) * 100);
  if (pct === 0) return <span className="diff">level</span>;
  const tone = higherIsBetter === undefined ? "" : (pct > 0) === higherIsBetter ? "good" : "bad";
  return <span className={`diff ${tone}`}>{pct > 0 ? "▲" : "▼"} {Math.abs(pct)}%</span>;
}

export default function Performance({ perf }) {
  if (!perf || perf.accounts.length === 0) {
    return (
      <section className="panel">
        <div className="empty">
          <b>No YouTube accounts yet</b>
          <span>Add our YouTube channel and competitors' channels in the Accounts tab, then click Refresh.</span>
        </div>
      </section>
    );
  }
  const { us, market } = perf;

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Us vs competitors on YouTube</h2>
            <p className="muted">Videos from the last {perf.days} days. "Typical views" is the median, so one viral video doesn't distort it.</p>
          </div>
        </div>

        {us && market ? (
          <div className="compare">
            {METRICS.map((m) => (
              <div className="compare-card" key={m.key}>
                <span className="card-label">{m.label}</span>
                <div className="compare-row">
                  <div><small>Us</small><b>{m.fmt(us[m.key])}</b></div>
                  <div><small>Competitors</small><b>{m.fmt(market[m.key])}</b></div>
                </div>
                <Diff us={us[m.key]} market={market[m.key]} higherIsBetter={m.higherIsBetter} />
              </div>
            ))}
          </div>
        ) : (
          <p className="notice">{us ? "No competitor posted in this period." : "Our channel has no videos in this period, or isn't marked as Ours."}</p>
        )}

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Channel</th><th>Subscribers</th><th>Videos</th><th>Per week</th><th>Typical views</th>
                <th>Avg views</th><th>Engagement</th><th>Avg length</th><th>Shorts</th><th>Best time (IST)</th>
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
                      <td className="nowrap small">{a.stats.best_time || "–"}</td>
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
      </section>

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
