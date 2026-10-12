import { compact } from "../api";

export default function OverviewCards({ data, perf }) {
  const us = perf?.us;
  const market = perf?.market;
  const cards = [
    { label: "Our posts", value: data?.our_posts, hint: "in the comparison period" },
    { label: "Competitor posts", value: data?.competitor_posts, hint: "in the comparison period" },
    { label: "Coverage gaps", value: data?.gaps, hint: "topics we missed", tone: data?.gaps ? "bad" : "" },
    {
      label: "Typical views (YouTube)",
      value: us ? compact(us.median_views) : undefined,
      hint: market ? `competitors: ${compact(market.median_views)}` : "add YouTube channels",
      tone: us && market ? (us.median_views >= market.median_views ? "good" : "bad") : "",
    },
    {
      label: "Engagement (YouTube)",
      value: us ? `${us.engagement_rate}%` : undefined,
      hint: market ? `competitors: ${market.engagement_rate}%` : "add YouTube channels",
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
