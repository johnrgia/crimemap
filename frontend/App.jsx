import { useState, useEffect, useCallback, useRef } from "react";

const API_BASE = "http://localhost:8000/api/v1";

// ============================================================================
// API helpers
// ============================================================================
async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// ============================================================================
// Constants
// ============================================================================
const BOSTON_CENTER = { lat: 42.3601, lng: -71.0589 };
const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || "__MAPBOX_TOKEN__";

const CATEGORY_COLORS = {
  "Violent Crime": "#EF4444",
  "Property Crime": "#F97316",
  "Drug Offenses": "#7C3AED",
  Traffic: "#3B82F6",
  Disturbance: "#EAB308",
  Fraud: "#10B981",
  Weapons: "#991B1B",
  "Medical/Service Call": "#0D9488",
  "Property (Non-Crime)": "#64748B",
  "Fire/Hazard": "#D97706",
  "Death Investigation": "#292524",
  Other: "#9CA3AF",
};

// ============================================================================
// Main App
// ============================================================================
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

  // Map ref
  const mapContainer = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef([]);

  // Load categories on mount
  useEffect(() => {
    fetchJSON(`${API_BASE}/categories`)
      .then(setCategories)
      .catch((e) => console.error("Failed to load categories:", e));
  }, []);

  // Search incidents
  const searchIncidents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let url = `${API_BASE}/incidents/search?latitude=${center.lat}&longitude=${center.lng}&radius_miles=${radius}&limit=2000`;
      if (categoryFilter) url += `&category=${encodeURIComponent(categoryFilter)}`;
      if (dateRange.from) url += `&from_date=${dateRange.from}T00:00:00`;
      if (dateRange.to) url += `&to_date=${dateRange.to}T23:59:59`;

      const data = await fetchJSON(url);
      setIncidents(data.incidents);

      // Also fetch stats
      let statsUrl = `${API_BASE}/stats?latitude=${center.lat}&longitude=${center.lng}&radius_miles=${radius}`;
      if (dateRange.from) statsUrl += `&from_date=${dateRange.from}T00:00:00`;
      if (dateRange.to) statsUrl += `&to_date=${dateRange.to}T23:59:59`;
      const statsData = await fetchJSON(statsUrl);
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

  // Initialize Mapbox
  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;
    if (MAPBOX_TOKEN === "__MAPBOX_TOKEN__") return;

    const script = document.createElement("script");
    script.src = "https://api.mapbox.com/mapbox-gl-js/v3.3.0/mapbox-gl.js";
    script.onload = () => {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = "https://api.mapbox.com/mapbox-gl-js/v3.3.0/mapbox-gl.css";
      document.head.appendChild(link);

      window.mapboxgl.accessToken = MAPBOX_TOKEN;
      const map = new window.mapboxgl.Map({
        container: mapContainer.current,
        style: "mapbox://styles/mapbox/dark-v11",
        center: [center.lng, center.lat],
        zoom: 13,
      });

      map.addControl(new window.mapboxgl.NavigationControl(), "top-right");

      map.on("click", (e) => {
        setCenter({ lat: e.lngLat.lat, lng: e.lngLat.lng });
      });

      mapRef.current = map;
    };
    document.head.appendChild(script);

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  // Update markers when incidents change
  useEffect(() => {
    if (!mapRef.current || !window.mapboxgl) return;

    // Clear old markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    incidents.forEach((inc) => {
      if (!inc.latitude || !inc.longitude) return;

      const el = document.createElement("div");
      el.style.width = "10px";
      el.style.height = "10px";
      el.style.borderRadius = "50%";
      el.style.backgroundColor = inc.color_hex || CATEGORY_COLORS[inc.category] || "#9CA3AF";
      el.style.border = "1.5px solid rgba(0,0,0,0.3)";
      el.style.cursor = "pointer";
      el.style.boxShadow = `0 0 6px ${inc.color_hex || "#9CA3AF"}44`;

      el.addEventListener("click", (e) => {
        e.stopPropagation();
        setSelectedIncident(inc);
      });

      const marker = new window.mapboxgl.Marker({ element: el })
        .setLngLat([inc.longitude, inc.latitude])
        .addTo(mapRef.current);

      markersRef.current.push(marker);
    });
  }, [incidents]);

  // Category breakdown from current results
  const categoryBreakdown = incidents.reduce((acc, inc) => {
    const cat = inc.category || "Unknown";
    acc[cat] = (acc[cat] || 0) + 1;
    return acc;
  }, {});

  const sortedCategories = Object.entries(categoryBreakdown).sort((a, b) => b[1] - a[1]);

  const needsMapboxToken = MAPBOX_TOKEN === "__MAPBOX_TOKEN__";

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
        {/* Sidebar */}
        <aside style={styles.sidebar}>
          {/* Filters */}
          <div style={styles.filterSection}>
            <h3 style={styles.filterTitle}>Search Filters</h3>

            <label style={styles.label}>Radius (miles)</label>
            <input
              type="range"
              min="0.1"
              max="10"
              step="0.1"
              value={radius}
              onChange={(e) => setRadius(parseFloat(e.target.value))}
              style={styles.slider}
            />
            <span style={styles.sliderValue}>{radius.toFixed(1)} mi</span>

            <label style={styles.label}>Category</label>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              style={styles.select}
            >
              <option value="">All Categories</option>
              {categories.map((g) => (
                <option key={g.category} value={g.category}>
                  {g.category}
                </option>
              ))}
            </select>

            <label style={styles.label}>From Date</label>
            <input
              type="date"
              value={dateRange.from}
              onChange={(e) => setDateRange((d) => ({ ...d, from: e.target.value }))}
              style={styles.input}
            />

            <label style={styles.label}>To Date</label>
            <input
              type="date"
              value={dateRange.to}
              onChange={(e) => setDateRange((d) => ({ ...d, to: e.target.value }))}
              style={styles.input}
            />
          </div>

          {/* Category Breakdown */}
          <div style={styles.breakdownSection}>
            <h3 style={styles.filterTitle}>Category Breakdown</h3>
            {sortedCategories.map(([cat, count]) => (
              <div key={cat} style={styles.breakdownRow}>
                <div style={styles.breakdownLeft}>
                  <span
                    style={{
                      ...styles.breakdownDot,
                      backgroundColor: CATEGORY_COLORS[cat] || "#9CA3AF",
                    }}
                  />
                  <span
                    style={{
                      ...styles.breakdownLabel,
                      ...(categoryFilter === cat ? { color: "#fff", fontWeight: 600 } : {}),
                    }}
                    onClick={() => setCategoryFilter(categoryFilter === cat ? "" : cat)}
                  >
                    {cat}
                  </span>
                </div>
                <span style={styles.breakdownCount}>{count}</span>
              </div>
            ))}
          </div>

          {/* Stats */}
          {stats && stats.total_incidents > 0 && (
            <div style={styles.statsSection}>
              <h3 style={styles.filterTitle}>Area Stats</h3>
              <div style={styles.statRow}>
                <span style={styles.statLabel}>Total Incidents</span>
                <span style={styles.statValue}>{stats.total_incidents.toLocaleString()}</span>
              </div>
              {stats.date_range.earliest && (
                <div style={styles.statRow}>
                  <span style={styles.statLabel}>Date Range</span>
                  <span style={styles.statValue}>
                    {new Date(stats.date_range.earliest).toLocaleDateString()} –{" "}
                    {new Date(stats.date_range.latest).toLocaleDateString()}
                  </span>
                </div>
              )}
            </div>
          )}
        </aside>

        {/* Main Content */}
        <div style={styles.content}>
          {error && <div style={styles.error}>Error: {error}</div>}

          {view === "map" ? (
            <div style={styles.mapWrapper}>
              {needsMapboxToken ? (
                <div style={styles.mapPlaceholder}>
                  <div style={styles.placeholderContent}>
                    <h2 style={styles.placeholderTitle}>Map View</h2>
                    <p style={styles.placeholderText}>
                      To enable the map, replace <code>__MAPBOX_TOKEN__</code> in{" "}
                      <code>App.jsx</code> with your Mapbox access token.
                    </p>
                    <p style={styles.placeholderText}>
                      Get a free token at{" "}
                      <a
                        href="https://mapbox.com"
                        target="_blank"
                        rel="noreferrer"
                        style={styles.link}
                      >
                        mapbox.com
                      </a>
                    </p>
                    <p style={styles.placeholderSubtext}>
                      Showing {incidents.length} incidents. Switch to List view to browse them.
                    </p>
                  </div>
                </div>
              ) : (
                <div ref={mapContainer} style={styles.map} />
              )}
            </div>
          ) : (
            <div style={styles.listWrapper}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Date</th>
                    <th style={styles.th}>Category</th>
                    <th style={styles.th}>Description</th>
                    <th style={styles.th}>Address</th>
                    <th style={styles.th}>Dist.</th>
                  </tr>
                </thead>
                <tbody>
                  {incidents.map((inc) => (
                    <tr
                      key={inc.id}
                      style={{
                        ...styles.tr,
                        ...(selectedIncident?.id === inc.id ? styles.trSelected : {}),
                      }}
                      onClick={() => setSelectedIncident(inc)}
                    >
                      <td style={styles.td}>
                        {inc.incident_date
                          ? new Date(inc.incident_date).toLocaleDateString("en-US", {
                              month: "short",
                              day: "numeric",
                              year: "2-digit",
                              hour: "numeric",
                              minute: "2-digit",
                            })
                          : "—"}
                      </td>
                      <td style={styles.td}>
                        <span
                          style={{
                            ...styles.categoryBadge,
                            backgroundColor: `${CATEGORY_COLORS[inc.category] || "#9CA3AF"}22`,
                            color: CATEGORY_COLORS[inc.category] || "#9CA3AF",
                            borderColor: `${CATEGORY_COLORS[inc.category] || "#9CA3AF"}44`,
                          }}
                        >
                          {inc.subcategory || inc.category}
                        </span>
                      </td>
                      <td style={styles.tdDesc}>{inc.description}</td>
                      <td style={styles.td}>{inc.address?.replace(", Boston, MA", "")}</td>
                      <td style={styles.tdDist}>
                        {inc.distance_miles ? `${inc.distance_miles.toFixed(2)} mi` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {incidents.length === 0 && !loading && (
                <div style={styles.emptyState}>No incidents found for this search.</div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Incident Detail Panel */}
      {selectedIncident && (
        <div style={styles.detailOverlay} onClick={() => setSelectedIncident(null)}>
          <div style={styles.detailPanel} onClick={(e) => e.stopPropagation()}>
            <button style={styles.detailClose} onClick={() => setSelectedIncident(null)}>
              ✕
            </button>
            <div
              style={{
                ...styles.detailCategory,
                color: CATEGORY_COLORS[selectedIncident.category] || "#9CA3AF",
              }}
            >
              {selectedIncident.category} / {selectedIncident.subcategory}
            </div>
            <h2 style={styles.detailTitle}>{selectedIncident.description}</h2>
            <div style={styles.detailGrid}>
              <DetailRow label="Date" value={
                selectedIncident.incident_date
                  ? new Date(selectedIncident.incident_date).toLocaleString()
                  : "Unknown"
              } />
              <DetailRow label="Address" value={selectedIncident.address || "Unknown"} />
              <DetailRow label="Department" value={selectedIncident.department_name} />
              <DetailRow
                label="Distance"
                value={
                  selectedIncident.distance_miles
                    ? `${selectedIncident.distance_miles.toFixed(3)} miles`
                    : "—"
                }
              />
              <DetailRow
                label="Coordinates"
                value={
                  selectedIncident.latitude
                    ? `${selectedIncident.latitude.toFixed(5)}, ${selectedIncident.longitude.toFixed(5)}`
                    : "Unknown"
                }
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DetailRow({ label, value }) {
  return (
    <div style={styles.detailRow}>
      <span style={styles.detailLabel}>{label}</span>
      <span style={styles.detailValue}>{value}</span>
    </div>
  );
}

// ============================================================================
// Styles
// ============================================================================
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
  sidebar: {
    width: "300px",
    flexShrink: 0,
    borderRight: "1px solid #1a1a2e",
    overflowY: "auto",
    backgroundColor: "#0d0d14",
    padding: "0",
  },
  filterSection: {
    padding: "20px",
    borderBottom: "1px solid #1a1a2e",
  },
  filterTitle: {
    fontSize: "11px",
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "1.5px",
    color: "#5a5a7a",
    marginTop: 0,
    marginBottom: "16px",
  },
  label: {
    display: "block",
    fontSize: "12px",
    color: "#7c7c9a",
    marginBottom: "6px",
    marginTop: "14px",
  },
  slider: {
    width: "100%",
    accentColor: "#3B82F6",
    cursor: "pointer",
  },
  sliderValue: {
    fontSize: "13px",
    color: "#a0a0b8",
    fontWeight: 600,
  },
  select: {
    width: "100%",
    padding: "8px 10px",
    fontSize: "13px",
    backgroundColor: "#12121e",
    border: "1px solid #1a1a2e",
    borderRadius: "6px",
    color: "#e2e2e8",
    outline: "none",
  },
  input: {
    width: "100%",
    padding: "8px 10px",
    fontSize: "13px",
    backgroundColor: "#12121e",
    border: "1px solid #1a1a2e",
    borderRadius: "6px",
    color: "#e2e2e8",
    outline: "none",
    boxSizing: "border-box",
  },
  breakdownSection: {
    padding: "20px",
    borderBottom: "1px solid #1a1a2e",
  },
  breakdownRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "5px 0",
  },
  breakdownLeft: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    flex: 1,
    minWidth: 0,
  },
  breakdownDot: {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    flexShrink: 0,
  },
  breakdownLabel: {
    fontSize: "12px",
    color: "#a0a0b8",
    cursor: "pointer",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  breakdownCount: {
    fontSize: "12px",
    color: "#5a5a7a",
    fontWeight: 600,
    fontVariantNumeric: "tabular-nums",
    marginLeft: "8px",
  },
  statsSection: {
    padding: "20px",
  },
  statRow: {
    display: "flex",
    justifyContent: "space-between",
    padding: "4px 0",
  },
  statLabel: { fontSize: "12px", color: "#7c7c9a" },
  statValue: { fontSize: "12px", color: "#e2e2e8", fontWeight: 500 },
  content: {
    flex: 1,
    overflow: "hidden",
    position: "relative",
  },
  mapWrapper: { width: "100%", height: "100%" },
  map: { width: "100%", height: "100%" },
  mapPlaceholder: {
    width: "100%",
    height: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#0a0a14",
    backgroundImage:
      "radial-gradient(circle at 50% 50%, #1a1a2e 0%, #0a0a14 70%)",
  },
  placeholderContent: { textAlign: "center", maxWidth: "400px", padding: "40px" },
  placeholderTitle: { fontSize: "24px", fontWeight: 700, color: "#f0f0f5", marginBottom: "12px" },
  placeholderText: { fontSize: "14px", color: "#7c7c9a", lineHeight: 1.6, marginBottom: "8px" },
  placeholderSubtext: { fontSize: "13px", color: "#5a5a7a", marginTop: "20px" },
  link: { color: "#3B82F6", textDecoration: "none" },
  listWrapper: {
    height: "100%",
    overflowY: "auto",
    padding: "0",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "13px",
  },
  th: {
    textAlign: "left",
    padding: "12px 16px",
    fontSize: "11px",
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "1px",
    color: "#5a5a7a",
    borderBottom: "1px solid #1a1a2e",
    position: "sticky",
    top: 0,
    backgroundColor: "#0d0d14",
    zIndex: 1,
  },
  tr: {
    cursor: "pointer",
    transition: "background-color 0.1s",
    borderBottom: "1px solid #111122",
  },
  trSelected: {
    backgroundColor: "#1a1a2e",
  },
  td: {
    padding: "10px 16px",
    color: "#c0c0d0",
    whiteSpace: "nowrap",
  },
  tdDesc: {
    padding: "10px 16px",
    color: "#e2e2e8",
    maxWidth: "300px",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  tdDist: {
    padding: "10px 16px",
    color: "#5a5a7a",
    fontVariantNumeric: "tabular-nums",
    textAlign: "right",
  },
  categoryBadge: {
    display: "inline-block",
    padding: "3px 8px",
    borderRadius: "4px",
    fontSize: "11px",
    fontWeight: 600,
    border: "1px solid",
    whiteSpace: "nowrap",
  },
  emptyState: {
    padding: "60px",
    textAlign: "center",
    color: "#5a5a7a",
    fontSize: "15px",
  },
  error: {
    padding: "12px 20px",
    backgroundColor: "#2d1215",
    color: "#f87171",
    fontSize: "13px",
    borderBottom: "1px solid #3d1a1e",
  },
  detailOverlay: {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(0,0,0,0.6)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1000,
    backdropFilter: "blur(4px)",
  },
  detailPanel: {
    backgroundColor: "#12121e",
    borderRadius: "12px",
    padding: "32px",
    maxWidth: "480px",
    width: "90%",
    border: "1px solid #1a1a2e",
    position: "relative",
    boxShadow: "0 24px 48px rgba(0,0,0,0.4)",
  },
  detailClose: {
    position: "absolute",
    top: "16px",
    right: "16px",
    background: "none",
    border: "none",
    color: "#5a5a7a",
    fontSize: "18px",
    cursor: "pointer",
    padding: "4px",
  },
  detailCategory: {
    fontSize: "12px",
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "1px",
    marginBottom: "8px",
  },
  detailTitle: {
    fontSize: "20px",
    fontWeight: 700,
    color: "#f0f0f5",
    marginTop: 0,
    marginBottom: "24px",
    lineHeight: 1.3,
  },
  detailGrid: {},
  detailRow: {
    display: "flex",
    justifyContent: "space-between",
    padding: "8px 0",
    borderBottom: "1px solid #1a1a2e",
  },
  detailLabel: { fontSize: "13px", color: "#5a5a7a" },
  detailValue: { fontSize: "13px", color: "#e2e2e8", textAlign: "right", maxWidth: "60%" },
};
