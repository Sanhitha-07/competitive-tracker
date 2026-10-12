import { useCallback, useEffect, useState } from "react";
import { fetchNews, getOrganizations, getResults } from "./api";
import OrgBar from "./components/OrgBar";
import OverviewCards from "./components/OverviewCards";
import Gaps from "./pages/Gaps";
import Speed from "./pages/Speed";
import Performance from "./pages/Performance";
import Suggestions from "./pages/Suggestions";
import Accounts from "./pages/Accounts";

const TABS = [
  { id: "suggestions", label: "Suggestions" },
  { id: "performance", label: "Performance" },
  { id: "gaps", label: "Coverage Gaps" },
  { id: "speed", label: "First to Publish" },
  { id: "accounts", label: "Accounts" },
];

function savedOrg() {
  try {
    return Number(localStorage.getItem("ct-org")) || null;
  } catch {
    return null;
  }
}

export default function App() {
  const [orgs, setOrgs] = useState([]);
  const [orgId, setOrgId] = useState(savedOrg);
  // A link ending in #performance (or another tab id) opens that tab.
  const [tab, setTab] = useState(() => {
    const fromLink = window.location.hash.slice(1);
    return TABS.some((t) => t.id === fromLink) ? fromLink : "suggestions";
  });
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [updatedAt, setUpdatedAt] = useState(null);

  // Load organizations; pick the saved one or the first.
  const loadOrgs = useCallback(async () => {
    try {
      const list = await getOrganizations();
      setOrgs(list);
      setOrgId((cur) => (list.some((o) => o.id === cur) ? cur : list[0]?.id ?? null));
      setError("");
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    }
  }, []);

  // If the API isn't up yet, keep trying every 3 seconds until it is.
  useEffect(() => {
    let timer;
    let stopped = false;
    const attempt = async () => {
      if (!(await loadOrgs()) && !stopped) timer = setTimeout(attempt, 3000);
    };
    attempt();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [loadOrgs]);

  async function tryAgain() {
    if (await loadOrgs()) loadResults();
  }

  const loadResults = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try {
      setResults(await getResults(orgId));
      setError("");
      setUpdatedAt(new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    try {
      if (orgId) localStorage.setItem("ct-org", String(orgId));
    } catch {
      // storage unavailable; ignore
    }
    setResults(null);
    setNotice("");
    loadResults();
  }, [orgId, loadResults]);

  async function refresh() {
    setNotice("");
    setRefreshing(true);
    try {
      const res = await fetchNews(orgId);
      const failed = (res.accounts || []).filter((a) => a.error).map((a) => a.account);
      setNotice(
        `${res.added} new ${res.added === 1 ? "item" : "items"} fetched.` +
          (failed.length ? ` Couldn't read: ${[...new Set(failed)].join(", ")}. See the Accounts tab.` : "")
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setRefreshing(false);
    }
    loadResults();
  }

  const lagging = results?.performance?.suggestions?.filter((s) => s.tone === "lagging").length;
  const counts = { suggestions: lagging, gaps: results?.gaps.length, speed: results?.speed.length };

  return (
    <div className="app">
      <header className="banner">
        <div>
          <span className="eyebrow">MediaOps</span>
          <h1>Competitive Tracker</h1>
          <p>Compare our content with competitors on news websites and YouTube: where we're lagging, what's working, and what to do next.</p>
        </div>
        <div className="banner-actions">
          <button className="btn light" onClick={refresh} disabled={!orgId || refreshing || loading}>
            {refreshing ? "Fetching…" : loading ? "Loading…" : "↻ Refresh"}
          </button>
          {updatedAt && (
            <span className="updated">Updated {updatedAt.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}</span>
          )}
        </div>
      </header>

      <OrgBar
        orgs={orgs}
        orgId={orgId}
        onSelect={setOrgId}
        onAdded={(org) => {
          setOrgs((list) => [...list, org].sort((a, b) => a.name.localeCompare(b.name)));
          setOrgId(org.id);
          setTab("accounts");
        }}
      />

      {error && (
        <div className="alert">
          <b>Something went wrong.</b> {error}
          <button className="btn ghost small-btn" onClick={tryAgain}>Try again</button>
        </div>
      )}
      {notice && <div className="notice">{notice}</div>}

      {!orgId ? (
        <section className="panel">
          <div className="empty">
            {error ? (
              <><b>Waiting for the API…</b><span>This page reconnects by itself once backend\run_api.bat is running.</span></>
            ) : (
              <><b>Add your first organization</b><span>Click "+ Add organization" above.</span></>
            )}
          </div>
        </section>
      ) : (
        <>
          <OverviewCards data={results?.overview} perf={results?.performance} />

          <nav className="tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                className={`tab ${tab === t.id ? "active" : ""}`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
                {counts[t.id] ? <span className="count">{counts[t.id]}</span> : null}
              </button>
            ))}
          </nav>

          {tab === "suggestions" && <Suggestions items={results?.performance?.suggestions} />}
          {tab === "performance" && <Performance perf={results?.performance} />}
          {tab === "gaps" && <Gaps gaps={results?.gaps || []} windowHours={results?.organization?.window_hours} />}
          {tab === "speed" && <Speed rows={results?.speed || []} />}
          {tab === "accounts" && <Accounts orgId={orgId} onChanged={loadResults} />}
        </>
      )}
    </div>
  );
}
