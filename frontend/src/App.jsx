import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchNews, getOptions, getOrganizations, getResults, setDisplayTimeZone } from "./api";
import OrgBar from "./components/OrgBar";
import OverviewCards from "./components/OverviewCards";
import Gaps from "./pages/Gaps";
import Speed from "./pages/Speed";
import Performance from "./pages/Performance";
import Suggestions from "./pages/Suggestions";
import Opportunities from "./pages/Opportunities";
import Explorer from "./pages/Explorer";
import Accounts from "./pages/Accounts";
import Workspace from "./pages/Workspace";

const TABS = [
  { id: "suggestions", label: "Suggestions" },
  { id: "opportunities", label: "Opportunities" },
  { id: "performance", label: "Performance" },
  { id: "gaps", label: "Coverage Gaps" },
  { id: "explorer", label: "Content Explorer" },
  { id: "speed", label: "First to Publish", onlyWhen: "time_sensitive" },
  { id: "accounts", label: "Accounts" },
  { id: "workspace", label: "Workspace" },
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
  const [options, setOptions] = useState(null);
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
  const [refreshKey, setRefreshKey] = useState(0); // tells tabs that load their own data to reload

  // Load workspaces and form options; pick the saved workspace or the first.
  const loadOrgs = useCallback(async () => {
    try {
      const [list, opts] = await Promise.all([getOrganizations(), getOptions()]);
      setOrgs(list);
      setOptions(opts);
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

  const loadResults = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try {
      const r = await getResults(orgId);
      setDisplayTimeZone(r.config?.timezone);
      setResults(r);
      setError("");
      setUpdatedAt(new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  async function tryAgain() {
    if (await loadOrgs()) loadResults();
  }

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

  useEffect(() => {
    if (window.location.hash.slice(1) !== tab) window.history.replaceState(null, "", `#${tab}`);
  }, [tab]);

  async function refresh() {
    setNotice("");
    setRefreshing(true);
    try {
      const res = await fetchNews(orgId);
      const failed = (res.accounts || []).filter((a) => a.error).map((a) => a.account);
      const questions = (res.accounts || []).reduce((n, a) => n + (a.questions || 0), 0);
      setNotice(
        `${res.added} new ${res.added === 1 ? "item" : "items"} fetched` +
          (questions ? `, ${questions} new audience question${questions === 1 ? "" : "s"}` : "") + "." +
          (failed.length ? ` Couldn't read: ${[...new Set(failed)].join(", ")}. See the Accounts tab.` : "") +
          (res.quota?.warning ? ` ${res.quota.warning}` : "")
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setRefreshing(false);
    }
    await loadResults();
    setRefreshKey((k) => k + 1);
  }

  const config = results?.config;
  const visibleTabs = TABS.filter((t) => !t.onlyWhen || config?.[t.onlyWhen] || (t.id === "speed" && results?.speed?.length));
  const recKeys = useMemo(() => new Set((results?.recommendations || []).map((r) => r.key)), [results]);
  const counts = {
    suggestions: results?.recommendations?.length,
    gaps: results?.overview?.topics_to_review,
    speed: results?.speed?.length,
  };
  const org = orgs.find((o) => o.id === orgId);
  const ytDefinitions = options?.platforms?.supported.find((p) => p.id === "youtube")?.metrics;

  return (
    <div className="app">
      <header className="banner">
        <div>
          <span className="eyebrow">MediaOps</span>
          <h1>Competitive Tracker</h1>
          <p>Compare your content with competitors on the platforms you use: what they cover that you don't, what's working for them, and what to make next.</p>
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
        config={config}
        options={options}
        onSelect={setOrgId}
        onAdded={(o) => {
          setOrgs((list) => [...list, o].sort((a, b) => a.name.localeCompare(b.name)));
          setOrgId(o.id);
          setTab("workspace");
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
              <><b>Add your first workspace</b><span>Click "+ Add workspace" above: for yourself, a client, or a brand.</span></>
            )}
          </div>
        </section>
      ) : (
        <>
          <OverviewCards data={results?.overview} perf={results?.performance} config={config} />

          <nav className="tabs" role="tablist">
            {visibleTabs.map((t) => (
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

          {tab === "suggestions" && (
            <Suggestions orgId={orgId} items={results?.recommendations} readiness={results?.readiness} config={config}
              onNavigate={setTab} onTracked={() => setRefreshKey((k) => k + 1)} />
          )}
          {tab === "opportunities" && <Opportunities orgId={orgId} onNavigate={setTab} refreshKey={refreshKey} />}
          {tab === "performance" && <Performance orgId={orgId} perf={results?.performance} definitions={ytDefinitions} refreshKey={refreshKey} />}
          {tab === "gaps" && (
            <Gaps orgId={orgId} gaps={results?.gaps || []} windowHours={results?.organization?.window_hours} config={config}
              recKeys={recKeys} onNavigate={setTab} refreshKey={refreshKey} />
          )}
          {tab === "explorer" && <Explorer orgId={orgId} refreshKey={refreshKey} />}
          {tab === "speed" && <Speed rows={results?.speed || []} />}
          {tab === "accounts" && <Accounts orgId={orgId} platforms={options?.platforms} onChanged={loadResults} />}
          {tab === "workspace" && (
            <Workspace
              orgId={orgId} org={org} config={config} options={options} onNavigate={setTab}
              onSaved={(o) => {
                setOrgs((list) => list.map((x) => (x.id === o.id ? o : x)));
                loadResults();
                setRefreshKey((k) => k + 1);
              }}
            />
          )}
        </>
      )}
    </div>
  );
}
