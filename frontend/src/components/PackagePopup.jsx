import { useState } from "react";
import { toIST } from "../api";

const PLATFORMS = ["X", "Facebook", "YouTube", "LinkedIn", "Instagram"];

export default function PackagePopup({ gap, onClose }) {
  const [heading, setHeading] = useState(gap.title);
  const [platforms, setPlatforms] = useState(["X", "Facebook", "YouTube"]);
  const [copied, setCopied] = useState("");

  const togglePlatform = (p) =>
    setPlatforms((cur) => (cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p]));

  const draftText = [
    `Heading: ${heading}`,
    `Priority: ${gap.priority}`,
    `Platforms: ${platforms.join(", ")}`,
    `Covered by: ${gap.covered_by.join(", ")}`,
    `First published: ${gap.first_by}, ${toIST(gap.first_published_at)} IST`,
    "Sources (for reference only, do not copy):",
    ...gap.links.map((l) => `- ${l}`),
  ].join("\n");

  async function copyDraft() {
    try {
      await navigator.clipboard.writeText(draftText);
      setCopied("Draft copied. Paste it into Draft Packages in MediaOps.");
    } catch {
      setCopied("Couldn't copy automatically. Select the text and copy it.");
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="popup" role="dialog" aria-modal="true" aria-labelledby="popup-title" onClick={(e) => e.stopPropagation()}>
        <div className="popup-head">
          <h2 id="popup-title">Create Package</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <label className="field">
          <span>Heading</span>
          <textarea id="pkg-heading" rows={2} value={heading} onChange={(e) => setHeading(e.target.value)} />
          <small className="warn-text">Rewrite this in our own words. Don't copy the competitor's headline.</small>
        </label>

        <div className="field">
          <span>Platforms</span>
          <div className="chips">
            {PLATFORMS.map((p) => (
              <button
                key={p}
                type="button"
                className={`chip ${platforms.includes(p) ? "on" : ""}`}
                onClick={() => togglePlatform(p)}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        <div className="meta-grid">
          <div><span>Priority</span><b className={`pill ${gap.priority === "P1" ? "p1" : "p2"}`}>{gap.priority}</b></div>
          <div><span>First published</span><b>{gap.first_by} · {toIST(gap.first_published_at)}</b></div>
          <div><span>Covered by</span><b>{gap.covered_by.join(", ")}</b></div>
        </div>

        <div className="field">
          <span>Sources</span>
          <ul className="sources">
            {gap.links.map((l) => (
              <li key={l}><a href={l} target="_blank" rel="noreferrer">{l}</a></li>
            ))}
          </ul>
        </div>

        <div className="popup-actions">
          <button className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={copyDraft} disabled={!heading.trim() || platforms.length === 0}>
            Copy draft
          </button>
        </div>
        {copied && <p className="toast">{copied}</p>}
      </div>
    </div>
  );
}
