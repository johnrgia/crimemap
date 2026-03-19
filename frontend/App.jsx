import { useState, useEffect, useCallback } from "react";
import { API_BASE, fetchJSON } from "./api.js";
import { BOSTON_CENTER } from "./constants.js";
import Sidebar from "./components/Sidebar.jsx";
import MapView from "./components/MapView.jsx";
import ListView from "./components/ListView.jsx";
import IncidentDetail from "./components/IncidentDetail.jsx";

export default function App() {
  const [incidents, setIncidents] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedIncident, setSelectedIncident] = useState(null);
  const [view, setView] = useState("map"); // "map" | "list"
  const [stats, setStats] = useState(null);

  // Filters
  const [radius, setRadius] = useState(1.0);
  const [center, setCenter] = useState(BOSTON_CENTER);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [dateRange, setDateRange] = useState({ from: "", to: "" });

  // Load categories once on mount
  useEffect(() => {
    fetchJSON(`${API_BASE}/categories`)
      .then(setCategories)
      .catch((e) => console.error("Failed to load categories:", e));
  }, []);

  // Search incidents whenever filters change
  const searchIncidents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let url = `${API_BASE}/incidents/search?latitude=${center.lat}&longitude=${center.lng}&radius_miles=${radius}&limit=2000`;
      if (categoryFilter) url += `&category=${encodeURIComponent(categoryFilter)}`;
      if (dateRange.from) url += `&from_date=${dateRange.from}T00:00:00`;
      if (dateRange.to) url += `&to_date=${dateRange.to}T23:59:59`;

      let statsUrl = `${API_BASE}/stats?latitude=${center.lat}&longitude=${center.lng}&radius_miles=${radius}`;
      if (dateRange.from) statsUrl += `&from_date=${dateRange.from}T00:00:00`;
      if (dateRange.to) statsUrl += `&to_date=${dateRange.to}T23:59:59`;

      const [data, statsData] = await Promise.all([fetchJSON(url), fetchJSON(statsUrl)]);
      setIncidents(data.incidents);
      setStats(statsData);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [center, radius, categoryFilter, dateRange]);

  useEffect(() => {
    searchIncidents();
  }, [searchIncidents]);

  // Category breakdown from current results
  const categoryBreakdown = incidents.reduce((acc, inc) => {
    const cat = inc.category || "Unknown";
    acc[cat] = (acc[cat] || 0) + 1;
    return acc;
  }, {});
  const sortedCategories = Object.entries(categoryBreakdown).sort((a, b) => b[1] - a[1]);

  return (
    <div style={styles.app}>
      {/* Header */}
      <header style={styles.header}>
        <div style={styles.headerLeft}>
          <h1 style={styles.logo}>
            <span style={styles.logoDot}>●</span> CrimeMap
          </h1>
          <span style={styles.badge}>BETA</span>
        </div>
        <div style={styles.headerRight}>
          <span style={styles.incidentCount}>
            {loading ? "..." : `${incidents.length.toLocaleString()} incidents`}
          </span>
          <button
            style={{ ...styles.viewToggle, ...(view === "map" ? styles.viewToggleActive : {}) }}
            onClick={() => setView("map")}
          >
            Map
          </button>
          <button
            style={{ ...styles.viewToggle, ...(view === "list" ? styles.viewToggleActive : {}) }}
            onClick={() => setView("list")}
          >
            List
          </button>
        </div>
      </header>

      <div style={styles.main}>
        <Sidebar
          radius={radius}
          setRadius={setRadius}
          categoryFilter={categoryFilter}
          setCategoryFilter={setCategoryFilter}
          categories={categories}
          dateRange={dateRange}
          setDateRange={setDateRange}
          sortedCategories={sortedCategories}
          stats={stats}
        />

        <div style={styles.content}>
          {error && <div style={styles.error}>Error: {error}</div>}
          {view === "map" ? (
            <MapView
              incidents={incidents}
              center={center}
              onCenterChange={setCenter}
              onIncidentSelect={setSelectedIncident}
            />
          ) : (
            <ListView
              incidents={incidents}
              loading={loading}
              selectedIncident={selectedIncident}
              onIncidentSelect={setSelectedIncident}
            />
          )}
        </div>
      </div>

      <IncidentDetail incident={selectedIncident} onClose={() => setSelectedIncident(null)} />
    </div>
  );
}

const styles = {
  app: {
    fontFamily: "'DM Sans', 'Helvetica Neue', sans-serif",
    backgroundColor: "#0a0a0f",
    color: "#e2e2e8",
    height: "100vh",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "12px 24px",
    borderBottom: "1px solid #1a1a2e",
    backgroundColor: "#0d0d14",
    flexShrink: 0,
  },
  headerLeft: { display: "flex", alignItems: "center", gap: "12px" },
  headerRight: { display: "flex", alignItems: "center", gap: "12px" },
  logo: {
    fontSize: "20px",
    fontWeight: 700,
    margin: 0,
    letterSpacing: "-0.5px",
    color: "#f0f0f5",
  },
  logoDot: { color: "#EF4444", marginRight: "2px" },
  badge: {
    fontSize: "10px",
    fontWeight: 700,
    padding: "2px 8px",
    borderRadius: "4px",
    backgroundColor: "#1a1a2e",
    color: "#7c7c9a",
    letterSpacing: "1px",
  },
  incidentCount: { fontSize: "13px", color: "#7c7c9a", marginRight: "8px" },
  viewToggle: {
    padding: "6px 16px",
    fontSize: "13px",
    fontWeight: 500,
    border: "1px solid #1a1a2e",
    borderRadius: "6px",
    backgroundColor: "transparent",
    color: "#7c7c9a",
    cursor: "pointer",
    transition: "all 0.15s",
  },
  viewToggleActive: {
    backgroundColor: "#1a1a2e",
    color: "#f0f0f5",
    borderColor: "#2a2a4e",
  },
  main: {
    display: "flex",
    flex: 1,
    overflow: "hidden",
  },
  content: {
    flex: 1,
    overflow: "hidden",
    position: "relative",
  },
  error: {
    padding: "12px 20px",
    backgroundColor: "#2d1215",
    color: "#f87171",
    fontSize: "13px",
    borderBottom: "1px solid #3d1a1e",
  },
};
