import { toIST } from "../api";

function delayTone(row) {
  if (row.we_were_first) return "good";
  return row.delay_minutes > 30 ? "bad" : "warn";
}

export default function Speed({ rows }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>First to Publish</h2>
          <p className="muted">Stories you covered that competitors also covered: who was first, and how late you were. Matched by headline similarity, so it suits time-sensitive content (news, launches, live events).</p>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="empty">
          <b>No shared stories yet</b>
          <span>When you and a competitor cover the same story, it appears here.</span>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Result</th>
                <th>Story</th>
                <th>First by</th>
                <th>Their time</th>
                <th>Your time</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.story_id}>
                  <td className="nowrap">
                    <span className={`pill ${delayTone(r)}`}>
                      {r.we_were_first ? "You were first" : `${r.delay_minutes} min late`}
                    </span>
                  </td>
                  <td className="story">{r.title}</td>
                  <td className="nowrap"><b>{r.first_by}</b></td>
                  <td className="nowrap num">{toIST(r.first_at)}</td>
                  <td className="nowrap num">{toIST(r.our_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
