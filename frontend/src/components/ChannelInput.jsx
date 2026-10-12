import { useEffect, useRef, useState } from "react";
import { compact, suggestChannels } from "../api";

const WAIT_MS = 600; // search only after typing pauses, to save YouTube quota

// Text box for a YouTube handle or link that suggests matching channels (with logo) while typing.
export default function ChannelInput({ id, value, onChange, onPick }) {
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [active, setActive] = useState(-1);
  const picked = useRef(false);
  const boxRef = useRef(null);

  useEffect(() => {
    const q = value.trim();
    // Links are used as they are; only search for names and handles.
    if (picked.current || q.length < 3 || /^https?:|youtube\.com|youtu\.be/i.test(q)) {
      picked.current = false;
      setResults([]);
      setOpen(false);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const list = await suggestChannels(q);
        if (!cancelled) {
          setResults(list);
          setError("");
          setOpen(true);
          setActive(list.length ? 0 : -1);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e.message);
          setOpen(true);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, WAIT_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [value]);

  // Close the list when clicking elsewhere.
  useEffect(() => {
    const close = (e) => boxRef.current && !boxRef.current.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  function pick(ch) {
    picked.current = true;
    setOpen(false);
    onPick(ch);
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
        placeholder="Type a channel name or @handle"
        autoComplete="off"
        role="combobox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
      />
      {loading && <span className="combo-spinner" aria-label="Searching" />}
      {open && (
        <ul className="combo-list" id={`${id}-list`} role="listbox">
          {error ? (
            <li className="combo-msg error-text">{error}</li>
          ) : results.length === 0 ? (
            <li className="combo-msg">No YouTube channels found. Check the spelling, or paste the channel link.</li>
          ) : (
            results.map((ch, i) => (
              <li
                key={ch.channel_id}
                role="option"
                aria-selected={i === active}
                className={`combo-item ${i === active ? "active" : ""}`}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(ch);
                }}
              >
                {ch.thumbnail ? <img src={ch.thumbnail} alt="" className="logo" /> : <span className="logo placeholder" />}
                <span className="combo-text">
                  <b>{ch.title}</b>
                  <span className="muted small">{ch.handle || ch.channel_id} · {compact(ch.subscribers)} subscribers</span>
                </span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
