import { ago, compact, fmtDate, fmtTime, FORMAT_LABEL } from "../api";

const CONF_TONE = { high: "good", medium: "warn", low: "bad" };

export function ConfidencePill({ confidence }) {
  if (!confidence) return null;
  return (
    <span className={`pill ${CONF_TONE[confidence.level]}`} title={confidence.reason}>
      {confidence.level} confidence
    </span>
  );
}

export function PostMini({ p }) {
  return (
    <a className="post-mini" href={p.link} target="_blank" rel="noreferrer">
      {p.thumbnail ? <img src={p.thumbnail} alt="" loading="lazy" /> : <span className="thumb-ph">{FORMAT_LABEL[p.format] || "Post"}</span>}
      <span className="post-mini-text">
        <b>{p.title}</b>
        <span className="muted small">
          {p.account}
          {p.views != null && <> · {compact(p.views)} views</>}
          {p.relative != null && <> · <span className={p.relative >= 1.2 ? "good-text" : ""}>{p.relative}× usual</span></>}
          {" · "}{fmtTime(p.published_at)}
        </span>
      </span>
    </a>
  );
}

function periodText(dp) {
  if (!dp) return "–";
  if (dp.from && dp.to) return `${fmtDate(dp.from)} – ${fmtDate(dp.to)}`;
  if (dp.days) return `last ${dp.days} days`;
  return dp.to ? `up to ${fmtDate(dp.to)}` : "–";
}

// "Why should I trust this?" for one recommendation or opportunity.
export default function Evidence({ rec, open = false }) {
  const ev = rec.evidence || {};
  return (
    <details className="evidence" open={open}>
      <summary>Evidence, sample size and limitations</summary>
      <div className="ev-grid">
        <div><span>Sample</span><b>{rec.sample?.text}</b></div>
        <div><span>Data period</span><b>{periodText(rec.data_period)}</b></div>
        <div><span>Confidence</span><b>{rec.confidence?.level}: {rec.confidence?.reason}</b></div>
        <div><span>Data freshness</span><b>Last refresh {ago(rec.freshness?.last_refresh)}</b></div>
      </div>

      {ev.metrics?.length > 0 && (
        <ul className="ev-metrics">
          {ev.metrics.map((m) => (
            <li key={m.label}>
              <span>{m.label}</span>
              <b>{typeof m.value === "number" ? m.value.toLocaleString("en-IN") : String(m.value)}</b>
              {m.definition && <small className="muted">{m.definition}</small>}
            </li>
          ))}
        </ul>
      )}

      {ev.posts?.length > 0 && (
        <div className="ev-block">
          <h4>Supporting posts</h4>
          <div className="post-mini-list">{ev.posts.map((p) => <PostMini key={p.id} p={p} />)}</div>
        </div>
      )}

      {ev.questions?.length > 0 && (
        <div className="ev-block">
          <h4>Public audience questions</h4>
          <ul className="questions">
            {ev.questions.map((q) => (
              <li key={q.id}>
                “{q.text}”
                <span className="muted small"> {q.likes} likes · on {q.is_us ? "your" : `${q.account}'s`} video “{q.on_post}”</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {rec.limitations?.length > 0 && (
        <div className="ev-block">
          <h4>Limitations</h4>
          <ul className="limits">{rec.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        </div>
      )}
      {rec.past_results && <p className="notice small">{rec.past_results}</p>}
    </details>
  );
}
