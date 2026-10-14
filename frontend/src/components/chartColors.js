// Colour follows the account, never its rank: "You" is always series 1 (the brand purple) and each
// competitor keeps the slot it gets here, in a fixed order, across every chart.
// The order is validated for colour-blind separation in light and dark (see index.css --series-*).
export const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)",
  "var(--series-5)", "var(--series-6)", "var(--series-7)"];

// accounts: [{name, is_us}] in a stable order (ours first). Returns name -> colour.
export function colorMap(accounts) {
  const map = {};
  let slot = 1;
  accounts.forEach((a) => {
    if (a.is_us) map[a.name] = SERIES[0];
    else map[a.name] = slot < SERIES.length ? SERIES[slot++] : "var(--series-other)";
  });
  return map;
}
