import { CATEGORY_COLORS } from "../constants.js";

export default function ListView({ incidents, loading, selectedIncident, onIncidentSelect }) {
  return (
    <div style={styles.wrapper}>
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
              onClick={() => onIncidentSelect(inc)}
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
                    ...styles.badge,
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
        <div style={styles.empty}>No incidents found for this search.</div>
      )}
    </div>
  );
}

const styles = {
  wrapper: {
    height: "100%",
    overflowY: "auto",
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
  badge: {
    display: "inline-block",
    padding: "3px 8px",
    borderRadius: "4px",
    fontSize: "11px",
    fontWeight: 600,
    border: "1px solid",
    whiteSpace: "nowrap",
  },
  empty: {
    padding: "60px",
    textAlign: "center",
    color: "#5a5a7a",
    fontSize: "15px",
  },
};
