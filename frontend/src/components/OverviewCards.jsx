import { compact, period } from "../api";

export default function OverviewCards({ data, perf, config }) {
  const us = perf?.us;
  const market = perf?.market;
  const inPeriod = `in ${period(config?.window_hours)}`;
  const cards = [
    { label: "Your posts", value: data?.our_posts, hint: inPeriod },
    { label: "Competitor posts", value: data?.competitor_posts, hint: inPeriod },
    {
      label: "Topics to review", value: data?.topics_to_review,
      hint: "competitors cover more than you", tone: data?.topics_to_review ? "warn" : "",
    },
    {
      label: "Typical views (YouTube)",
      value: us ? compact(us.median_views) : undefined,
      hint: market ? `competitors: ${compact(market.median_views)} · last ${perf.days} days` : "add YouTube channels",
      tone: us && market ? (us.median_views >= market.median_views ? "good" : "bad") : "",
    },
    {
      label: "Engagement (YouTube)",
      value: us ? `${us.engagement_rate}%` : undefined,
      hint: market ? `competitors: ${market.engagement_rate}% · (likes+comments) ÷ views` : "add YouTube channels",
      tone: us && market ? (us.engagement_rate >= market.engagement_rate ? "good" : "bad") : "",
    },
  ];
  return (
    <div className="cards">
      {cards.map((c) => (
        <div className="card" key={c.label}>
          <span className="card-label">{c.label}</span>
          <span className={`card-value ${c.tone || ""}`}>{c.value ?? "–"}</span>
          <span className="card-hint">{c.hint}</span>
        </div>
      ))}
    </div>
  );
}
