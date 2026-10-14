import { useEffect, useMemo, useState } from "react";
import { ago, AUDIENCE_WORD, compact, fmtDate, FORMAT_LABEL, getAiBriefing, getDashboard, PLATFORM_LABEL, TAB_LABEL, tzLabel } from "../api";
import { BarList, ColumnChart, Heatmap, Legend, PairedBars, Sparkline } from "../components/charts";
import { colorMap } from "../components/chartColors";
import { PostMini } from "../components/Evidence";
import { SensitivityBadge } from "./Trends";

const TONE_ICON = { good: "✓", bad: "↓", warn: "!", info: "i" };
const TONE_WORD = { good: "Strength", bad: "Behind", warn: "Needs attention", info: "Good to know" };

function Kpis({ items }) {
  return (
    <div className="kpis">
      {items.map((k) => (
        <div className="kpi" key={k.id}>
          <span className="kpi-label">{k.label}</span>
          <span className={`kpi-value ${k.tone || ""}`}>{k.value ?? "–"}</span>
          <span className="kpi-hint">{k.hint}</span>
        </div>
      ))}
    </div>
  );
}

function Briefing({ data, onNavigate }) {
  return (
    <section className="panel briefing">
      <div className="panel-head">
        <div>
          <span className="eyebrow-dark">What's happening</span>
          <h2 className="headline">{data.headline}</h2>
        </div>
      </div>
      {data.items.length === 0 ? (
        <p className="muted">Nothing to report yet. Add accounts and click Refresh.</p>
      ) : (
        <ul className="brief-list">
          {data.items.map((x) => (
            <li key={x.title} className={`brief ${x.tone}`}>
              <span className="brief-icon" aria-label={TONE_WORD[x.tone]} title={TONE_WORD[x.tone]}>{TONE_ICON[x.tone]}</span>
              <div>
                <b>{x.title}</b>
                <p>{x.text}</p>
                {x.tab && x.tab !== "dashboard" && (
                  <button className="link-btn small" onClick={() => onNavigate(x.tab)}>See details in {TAB_LABEL[x.tab] || x.tab} →</button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Priorities({ items, onNavigate }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow-dark">Do this next</span>
          <h2>Top actions</h2>
        </div>
      </div>
      {items.length === 0 ? (
        <p className="muted">Actions appear when your data supports them.</p>
      ) : (
        <ol className="prio-list">
          {items.map((p) => (
            <li key={p.key}>
              <span className="kind">{p.kind_label}{p.platform ? ` · ${PLATFORM_LABEL[p.platform] || p.platform}` : ""}</span>
              <b>{p.title}</b>
              <span className="muted small">{p.next_step}</span>
            </li>
          ))}
        </ol>
      )}
      <button className="btn ghost small-btn" onClick={() => onNavigate("suggestions")}>All suggestions with evidence →</button>
    </section>
  );
}

function AiPanel({ orgId, available }) {
  const [state, setState] = useState({ loading: false, data: null, error: "" });
  async function run() {
    setState({ loading: true, data: null, error: "" });
    try {
      setState({ loading: false, data: await getAiBriefing(orgId), error: "" });
    } catch (e) {
      setState({ loading: false, data: null, error: e.message });
    }
  }
  if (!available) {
    return (
      <p className="muted small ai-off">
        Optional: add an <code>ANTHROPIC_API_KEY</code> to <code>backend\.env</code> to get an AI-written briefing and content ideas from these numbers.
      </p>
    );
  }
  const d = state.data;
  return (
    <section className="panel ai-panel">
      <div className="panel-head">
        <div>
          <span className="eyebrow-dark">AI briefing</span>
          <h2>Strategist's summary</h2>
          <p className="muted small">Written by AI from the numbers on this page only. Check anything important against the evidence.</p>
        </div>
        <button className="btn primary small-btn" onClick={run} disabled={state.loading}>
          {state.loading ? "Writing…" : d ? "Write again" : "Write AI briefing"}
        </button>
      </div>
      {state.error && <p className="error-text">{state.error}</p>}
      {d && (
        <>
          <p className="ai-summary">{d.summary}</p>
          {d.priorities?.length > 0 && (
            <div className="ai-grid">
              {d.priorities.map((p) => (
                <div className="ai-card" key={p.title}>
                  <b>{p.title}</b>
                  <p className="small"><span className="lbl">Why:</span> {p.why}</p>
                  <p className="small"><span className="lbl">Do:</span> {p.action}</p>
                </div>
              ))}
            </div>
          )}
          {d.content_ideas?.length > 0 && (
            <>
              <h3 className="sub-h">Content ideas</h3>
              <ul className="ideas">
                {d.content_ideas.map((i) => (
                  <li key={i.idea}>
                    <b>{i.idea}</b>
                    <span className="muted small"> · {i.format} · from {i.based_on}</span>
                    {i.caution && <div className="warn-text">{i.caution}</div>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}

function ShareOfVoice({ sov, colors }) {
  const [by, setBy] = useState(sov.total_interactions ? "interactions" : "posts");
  const rows = sov.rows.map((r) => ({
    name: r.name, is_us: r.is_us, color: colors[r.name],
    value: by === "posts" ? r.share_posts : r.share_interactions,
    label: `${by === "posts" ? r.share_posts : r.share_interactions}%`,
    tip: by === "posts" ? `${r.posts} posts (${r.share_posts}% of all)` : `${compact(r.interactions)} interactions (${r.share_interactions}% of all)`,
  })).sort((a, b) => b.value - a.value);
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Share of voice</h2>
          <p className="muted small">{sov.definition}</p>
        </div>
        <div className="chips" role="tablist">
          <button className={`chip ${by === "interactions" ? "on" : ""}`} onClick={() => setBy("interactions")} disabled={!sov.total_interactions}>Attention</button>
          <button className={`chip ${by === "posts" ? "on" : ""}`} onClick={() => setBy("posts")}>Posts</button>
        </div>
      </div>
      <BarList rows={rows} max={100} format={(v) => `${v}%`} />
    </section>
  );
}

function Activity({ activity, colors, legend }) {
  const labelOf = (b) => {
    const d = new Date(b + "T00:00:00");
    return activity.unit === "day" ? d.toLocaleDateString("en-IN", { weekday: "short" }) : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  };
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Posting activity</h2>
          <p className="muted small">Posts per {activity.unit} across all platforms ({activity.unit === "day" ? "last 7 days" : "last 8 weeks"}).</p>
        </div>
      </div>
      <Legend items={legend} />
      <ColumnChart buckets={activity.buckets} series={activity.series} colors={colors} labelOf={labelOf} />
    </section>
  );
}

function Engagement({ blocks, colors }) {
  if (!blocks.length) return null;
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Engagement by platform</h2>
          <p className="muted small">Each platform is compared only with itself: YouTube by views, Instagram and Facebook by followers.</p>
        </div>
      </div>
      <div className="eng-grid">
        {blocks.map((b) => (
          <div key={b.platform}>
            <h3 className="sub-h"><span className={`plat ${b.platform}`}>{b.label}</span> engagement rate</h3>
            <BarList rows={b.rows.filter((r) => r.value != null).map((r) => ({
              name: r.name, is_us: r.is_us, color: colors[r.name], value: r.value, label: `${r.value}%`,
              tip: `${r.value}% · typical post: ${compact(r.typical)} ${b.platform === "youtube" ? "views" : "interactions"}`,
            })).sort((x, y) => y.value - x.value)} format={(v) => `${v}%`} />
            <p className="muted small def">{b.definition}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Formats({ mix }) {
  if (!mix.rows.length) return null;
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Content formats</h2>
          <p className="muted small">Share of posts per format: you ({mix.our_total}) vs competitors ({mix.their_total}).</p>
        </div>
      </div>
      <Legend items={[{ name: "You", color: "var(--series-1)" }, { name: "Competitors", color: "var(--series-muted)" }]} />
      <PairedBars rows={mix.rows.slice(0, 7).map((r) => ({ label: FORMAT_LABEL[r.format] || r.format, ours: r.ours_pct, theirs: r.theirs_pct, oursN: r.ours, theirsN: r.theirs }))} />
    </section>
  );
}

function BestTimes({ data }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>When competitors' posts do best</h2>
          <p className="muted small">{data.definition} Times in {tzLabel()}.</p>
        </div>
      </div>
      {data.best.length > 0 && (
        <p className="small"><b>Strongest slots:</b> {data.best.map((c) => `${c.day} ${c.slot.toLowerCase()} (${c.median_relative}×)`).join(" · ")}</p>
      )}
      <Heatmap data={data} />
    </section>
  );
}

function TrendsNow({ trends, onNavigate }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Trending now, for you</h2>
          <p className="muted small">Internet trends that match your workspace, rated for sensitivity for your kind of business.</p>
        </div>
        <button className="btn ghost small-btn" onClick={() => onNavigate("trends")}>All trends →</button>
      </div>
      {trends.length === 0 ? (
        <p className="muted">No matching trends yet. Add topics in Workspace settings and click Refresh.</p>
      ) : (
        <ul className="trend-mini">
          {trends.map((t) => (
            <li key={t.key}>
              <div className="trend-mini-head">
                <b>{t.title}</b>
                {t.rising && <span className="pill good tiny">rising</span>}
                <SensitivityBadge t={t} />
              </div>
              <span className="muted small">{t.signal}</span>
              <span className="small">{t.coverage.text}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Audience({ rows }) {
  const shown = rows.filter((r) => r.audience != null);
  if (!shown.length) return null;
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Audience size</h2>
          <p className="muted small">Followers / subscribers now, and the change since the first refresh in this period.</p>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Account</th><th>Platform</th><th className="num">Audience</th><th className="num">Change</th><th>Trend</th></tr></thead>
          <tbody>
            {shown.sort((a, b) => (b.is_us - a.is_us) || (b.audience - a.audience)).map((r) => (
              <tr key={r.id} className={r.is_us ? "us-row" : ""}>
                <td><b>{r.name}</b></td>
                <td><span className={`plat ${r.platform}`}>{PLATFORM_LABEL[r.platform]}</span></td>
                <td className="num">{compact(r.audience)} <span className="muted small">{AUDIENCE_WORD[r.platform]}</span></td>
                <td className="num">{r.change == null ? <span className="muted small">needs 2+ refreshes</span>
                  : <span className={r.change >= 0 ? "good-text" : "bad-text"}>{r.change >= 0 ? "+" : ""}{compact(r.change)}{r.change_pct != null ? ` (${r.change_pct}%)` : ""}</span>}</td>
                <td><Sparkline points={r.points} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function Dashboard({ orgId, refreshKey, onNavigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    setError("");
    getDashboard(orgId).then((d) => live && setData(d)).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [orgId, refreshKey]);

  const colors = useMemo(() => colorMap(data?.activity.series || []), [data]);
  const legend = useMemo(() => (data?.activity.series || []).map((s) => ({ name: s.name, is_us: s.is_us, color: colors[s.name] })), [data, colors]);

  if (error) return <section className="panel"><div className="empty"><b>Dashboard not available</b><span>{error}</span></div></section>;
  if (!data) return <section className="panel"><div className="empty"><b>Loading dashboard…</b></div></section>;

  if (!data.accounts.ours && !data.accounts.competitors) {
    return (
      <section className="panel">
        <div className="empty">
          <b>Let's set up this workspace</b>
          <span>1. Tell us about the business in Workspace settings. 2. Add your own accounts and 3–5 competitors. 3. Click Refresh.</span>
          <div className="center chips">
            <button className="btn primary small-btn" onClick={() => onNavigate("workspace")}>Workspace settings</button>
            <button className="btn ghost small-btn" onClick={() => onNavigate("accounts")}>Add accounts</button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <div className="dash">
      <div className="dash-meta muted small">
        Last {data.period.days} days ({fmtDate(data.period.from)} – {fmtDate(data.period.to)}) · data refreshed {ago(data.freshness.last_refresh)}
        {" · "}{data.accounts.competitors} competitor{data.accounts.competitors === 1 ? "" : "s"} on {data.accounts.platforms.map((p) => PLATFORM_LABEL[p] || p).join(", ")}
      </div>
      <Kpis items={data.kpis} />
      <div className="dash-grid two">
        <Briefing data={data.briefing} onNavigate={onNavigate} />
        <Priorities items={data.priorities} onNavigate={onNavigate} />
      </div>
      <AiPanel orgId={orgId} available={data.ai_available} />
      <div className="dash-grid two">
        <ShareOfVoice sov={data.share_of_voice} colors={colors} />
        <TrendsNow trends={data.trends} onNavigate={onNavigate} />
      </div>
      <Activity activity={data.activity} colors={colors} legend={legend} />
      <div className="dash-grid two">
        <Engagement blocks={data.engagement} colors={colors} />
        <Formats mix={data.format_mix} />
      </div>
      <BestTimes data={data.best_times} />
      <div className="dash-grid two">
        <section className="panel">
          <div className="panel-head"><div><h2>Competitors' standout posts</h2><p className="muted small">Furthest above their own account's usual. Learn from them, don't copy.</p></div></div>
          {data.top_posts.competitors.length ? <div className="post-col">{data.top_posts.competitors.map((p) => <PostMini key={p.id} p={p} />)}</div>
            : <p className="muted">Needs 5+ posts per account with public numbers.</p>}
        </section>
        <section className="panel">
          <div className="panel-head"><div><h2>Your best posts</h2><p className="muted small">Compared with your own usual on each platform.</p></div></div>
          {data.top_posts.ours.length ? <div className="post-col">{data.top_posts.ours.map((p) => <PostMini key={p.id} p={p} />)}</div>
            : <p className="muted">Needs 5+ of your posts with public numbers.</p>}
        </section>
      </div>
      <Audience rows={data.audience} />
    </div>
  );
}
