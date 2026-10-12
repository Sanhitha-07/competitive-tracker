const GROUPS = [
  { tone: "lagging", label: "Where we're lagging" },
  { tone: "good", label: "What we're doing well" },
  { tone: "info", label: "Worth trying" },
];

export default function Suggestions({ items }) {
  if (!items || items.length === 0) {
    return (
      <section className="panel">
        <div className="empty">
          <b>No suggestions yet</b>
          <span>Suggestions appear once our YouTube channel and at least one competitor's channel have videos. Check the Accounts tab and click Refresh.</span>
        </div>
      </section>
    );
  }
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Suggestions</h2>
          <p className="muted">Based on how our channel compares with competitors on the Performance tab, plus topics we haven't covered.</p>
        </div>
      </div>
      {GROUPS.map((g) => {
        const list = items.filter((s) => s.tone === g.tone);
        if (list.length === 0) return null;
        return (
          <div key={g.tone} className="sugg-group">
            <h3>{g.label}</h3>
            {list.map((s) => (
              <div key={s.title} className={`sugg ${s.tone}`}>
                <b>{s.title}</b>
                <p>{s.detail}</p>
              </div>
            ))}
          </div>
        );
      })}
    </section>
  );
}
