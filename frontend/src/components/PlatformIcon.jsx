// Small platform marks for lists and status rows (simple drawn glyphs, not official brand assets).
const PATHS = {
  instagram: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx="17.3" cy="6.7" r="1.3" fill="currentColor" />
    </>
  ),
  facebook: <path fill="currentColor" d="M13.5 21v-7.5h2.6l.4-3h-3V8.6c0-.9.3-1.5 1.5-1.5h1.6V4.4c-.3 0-1.2-.1-2.3-.1-2.3 0-3.8 1.4-3.8 3.9v2.3H7.9v3h2.6V21h3z" />,
  x: <path fill="currentColor" d="M4 4h4.6l3.9 5.3L17 4h3l-6 6.9L21 20h-4.6l-4.2-5.7L7 20H4l6.7-7.6L4 4z" />,
  youtube: (
    <>
      <rect x="2" y="5" width="20" height="14" rx="4" fill="currentColor" />
      <path d="M10 9l5 3-5 3V9z" fill="#fff" />
    </>
  ),
  rss: (
    <>
      <circle cx="6" cy="18" r="2" fill="currentColor" />
      <path d="M4 11a9 9 0 019 9M4 4a16 16 0 0116 16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </>
  ),
};

export default function PlatformIcon({ platform, size = 20 }) {
  return (
    <span className={`pf-icon ${platform}`} aria-hidden="true">
      <svg viewBox="0 0 24 24" width={size} height={size}>{PATHS[platform] || PATHS.rss}</svg>
    </span>
  );
}
