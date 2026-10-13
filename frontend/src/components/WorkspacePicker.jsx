import { useEffect, useRef, useState } from "react";
import { deleteOrganization } from "../api";
import Popup from "./Popup";

// Workspace dropdown with a "−" button on each row to remove that workspace (asks to confirm first).
export default function WorkspacePicker({ orgs, orgId, onSelect, onRemoved }) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(null); // the workspace waiting for confirmation
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState("");
  const boxRef = useRef(null);
  const current = orgs.find((o) => o.id === orgId);

  // Close the list when clicking elsewhere or pressing Escape.
  useEffect(() => {
    if (!open) return;
    const onClick = (e) => boxRef.current && !boxRef.current.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function askToRemove(org) {
    setOpen(false);
    setError("");
    setConfirming(org);
  }

  async function remove() {
    setRemoving(true);
    try {
      await deleteOrganization(confirming.id);
      onRemoved(confirming.id);
      setConfirming(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setRemoving(false);
    }
  }

  return (
    <div className="ws-picker" ref={boxRef}>
      <button
        id="org-select"
        type="button"
        className="ws-current"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        disabled={orgs.length === 0}
      >
        <span>{current ? current.name : "No workspaces yet"}</span>
        <span className="ws-caret" aria-hidden="true">▾</span>
      </button>

      {open && (
        <ul className="ws-list" role="listbox" aria-label="Workspaces">
          {orgs.map((o) => (
            <li key={o.id} className={`ws-item ${o.id === orgId ? "selected" : ""}`} role="option" aria-selected={o.id === orgId}>
              <button
                type="button"
                className="ws-name"
                onClick={() => {
                  onSelect(o.id);
                  setOpen(false);
                }}
              >
                {o.name}
              </button>
              <button
                type="button"
                className="ws-remove"
                title={`Remove ${o.name}`}
                aria-label={`Remove workspace ${o.name}`}
                onClick={() => askToRemove(o)}
              >
                −
              </button>
            </li>
          ))}
        </ul>
      )}

      {confirming && (
        <Popup title="Remove workspace?" onClose={() => !removing && setConfirming(null)}>
          <p>
            Remove <b>{confirming.name}</b>? This permanently deletes its accounts, collected posts and videos,
            suggestions history and opportunities. It can't be undone.
          </p>
          {error && <p className="error-text">{error}</p>}
          <div className="popup-actions">
            <button className="btn ghost" onClick={() => setConfirming(null)} disabled={removing}>Cancel</button>
            <button className="btn danger" onClick={remove} disabled={removing}>
              {removing ? "Removing…" : "Remove workspace"}
            </button>
          </div>
        </Popup>
      )}
    </div>
  );
}
