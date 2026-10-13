import { useEffect, useRef, useState } from "react";
import { compact, suggestProfiles } from "../api";

const WAIT_MS = 700; // look up only after typing pauses (X bills each lookup)

// Username / link box for Instagram, Facebook and X that suggests matching profiles while typing,
// like the YouTube channel box. Instagram and Facebook can only match an exact username or Page name;
// X searches by name when the X plan allows it. Before the platform is connected, a short note shows instead.
export default function ProfileInput({ id, orgId, platform, label, value, onChange, onPick, placeholder }) {
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState("");
  const [active, setActive] = useState(-1);
  const picked = useRef(false);
  const boxRef = useRef(null);

  useEffect(() => {
    const q = value.trim();
    if (picked.current || q.replace(/^@/, "").length < 2) {
      picked.current = false;
      setResults([]);
      setOpen(false);
      if (!q) setNote("");
      return;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await suggestProfiles(orgId, platform, q);
        if (cancelled) return;
        setResults(r.results || []);
        setNote(r.note || "");
        setOpen(r.available && (r.results?.length > 0 || Boolean(r.note)));
        setActive(r.results?.length ? 0 : -1);
      } catch (e) {
        if (!cancelled) {
          setResults([]);
          // 404 = an older API without profile suggestions is running; anything else = lookup failed.
          setNote(e.status === 404
            ? "Profile suggestions need the latest API. Restart backend\\run_api.bat, then try again."
            : `Couldn't look up profiles right now (${e.message}). You can still type the full username and add it.`);
          setOpen(false);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, WAIT_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [value, orgId, platform]);

  // Close the list when clicking elsewhere.
  useEffect(() => {
    const close = (e) => boxRef.current && !boxRef.current.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  function pick(p) {
    picked.current = true;
    setOpen(false);
    setNote("");
    onPick(p);
  }

  function onKeyDown(e) {
    if (!open || results.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i - 1 + results.length) % results.length);
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      pick(results[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="combo" ref={boxRef}>
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        onFocus={() => results.length && setOpen(true)}
        placeholder={placeholder}
        autoComplete="off"
        role="combobox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        aria-describedby={`${id}-note`}
      />
      {loading && <span className="combo-spinner" aria-label="Searching" />}
      {open && (
        <ul className="combo-list" id={`${id}-list`} role="listbox">
          {results.length === 0 ? (
            <li className="combo-msg">{note || `No ${label} profile found.`}</li>
          ) : (
            results.map((p, i) => (
              <li
                key={p.external_id || p.source}
                role="option"
                aria-selected={i === active}
                className={`combo-item ${i === active ? "active" : ""}`}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(p);
                }}
              >
                {p.thumbnail ? <img src={p.thumbnail} alt="" className="logo" /> : <span className="logo placeholder" />}
                <span className="combo-text">
                  <b>{p.display_name || p.source}</b>
                  <span className="muted small">
                    {platform === "facebook" ? p.source : `@${p.source}`}
                    {p.subscribers !== null && p.subscribers !== undefined && ` · ${compact(p.subscribers)} followers`}
                  </span>
                </span>
              </li>
            ))
          )}
        </ul>
      )}
      {!open && note && <small id={`${id}-note`} className="muted combo-note">{note}</small>}
    </div>
  );
}
