import { useEffect, useId } from "react";

// A dialog over the page. Closes on Escape, on the ✕ button, or by clicking outside it.
export default function Popup({ title, onClose, children, wide = false }) {
  const titleId = useId();
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="overlay" onClick={onClose}>
      <div className={`popup ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" aria-labelledby={titleId} onClick={(e) => e.stopPropagation()}>
        <div className="popup-head">
          <h2 id={titleId}>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}
