import { useState } from "react";
import { PLATFORM_LABEL, toIST } from "../api";
import PackagePopup from "../components/PackagePopup";

function period(hours) {
  if (!hours) return "recently";
  return hours >= 48 ? `in the last ${Math.round(hours / 24)} days` : `in the last ${hours} hours`;
}

export default function Gaps({ gaps, windowHours }) {
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState("");

  const shown = gaps.filter((g) => g.title.toLowerCase().includes(search.toLowerCase()));

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Coverage Gaps</h2>
          <p className="muted">Topics that 2 or more competitors covered and we didn't, {period(windowHours)}.</p>
        </div>
        <input
          id="gap-search"
          className="search"
          placeholder="Search stories…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {shown.length === 0 ? (
        <div className="empty">
          <b>{gaps.length === 0 ? "No gaps right now" : "No stories match your search"}</b>
          <span>{gaps.length === 0 ? "We covered every story that competitors covered." : "Try a different word."}</span>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Priority</th>
                <th>Story</th>
                <th>Covered by</th>
                <th>First published</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((g) => (
                <tr key={g.story_id}>
                  <td><span className={`pill ${g.priority === "P1" ? "p1" : "p2"}`}>{g.priority}</span></td>
                  <td className="story">
                    {g.title}
                    <div className="plats">
                      {(g.platforms || []).map((p) => <span key={p} className={`plat ${p}`}>{PLATFORM_LABEL[p]}</span>)}
                    </div>
                  </td>
                  <td>
                    <div className="chips">
                      {g.covered_by.map((c) => <span className="chip static" key={c}>{c}</span>)}
                    </div>
                  </td>
                  <td className="nowrap">
                    <b>{g.first_by}</b>
                    <div className="muted small">{toIST(g.first_published_at)}</div>
                  </td>
                  <td>
                    <button className="btn primary small-btn" onClick={() => setSelected(g)}>Create Package</button>
                  </td>
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
