import { CATEGORY_COLORS } from "../constants.js";

export default function Sidebar({
  radius,
  setRadius,
  categoryFilter,
  setCategoryFilter,
  categories,
  dateRange,
  setDateRange,
  sortedCategories,
  stats,
}) {
  return (
    <aside style={styles.sidebar}>
      {/* Filters */}
      <div style={styles.section}>
        <h3 style={styles.sectionTitle}>Search Filters</h3>

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
      <div style={styles.section}>
        <h3 style={styles.sectionTitle}>Category Breakdown</h3>
        {sortedCategories.map(([cat, count]) => (
          <div key={cat} style={styles.breakdownRow}>
            <div style={styles.breakdownLeft}>
              <span
                style={{
                  ...styles.dot,
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
        <div style={styles.section}>
          <h3 style={styles.sectionTitle}>Area Stats</h3>
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
  );
}

const styles = {
  sidebar: {
    width: "300px",
    flexShrink: 0,
    borderRight: "1px solid #1a1a2e",
    overflowY: "auto",
    backgroundColor: "#0d0d14",
  },
  section: {
    padding: "20px",
    borderBottom: "1px solid #1a1a2e",
  },
  sectionTitle: {
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
  dot: {
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
  statRow: {
    display: "flex",
    justifyContent: "space-between",
    padding: "4px 0",
  },
  statLabel: { fontSize: "12px", color: "#7c7c9a" },
  statValue: { fontSize: "12px", color: "#e2e2e8", fontWeight: 500 },
};
