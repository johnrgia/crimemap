import { CATEGORY_COLORS } from "../constants.js";

export default function IncidentDetail({ incident, onClose }) {
  if (!incident) return null;

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.panel} onClick={(e) => e.stopPropagation()}>
        <button style={styles.close} onClick={onClose}>✕</button>
        <div
          style={{
            ...styles.category,
            color: CATEGORY_COLORS[incident.category] || "#9CA3AF",
          }}
        >
          {incident.category} / {incident.subcategory}
        </div>
        <h2 style={styles.title}>{incident.description}</h2>
        <div>
          <DetailRow
            label="Date"
            value={incident.incident_date ? new Date(incident.incident_date).toLocaleString() : "Unknown"}
          />
          <DetailRow label="Address" value={incident.address || "Unknown"} />
          <DetailRow label="Department" value={incident.department_name} />
          <DetailRow
            label="Distance"
            value={incident.distance_miles ? `${incident.distance_miles.toFixed(3)} miles` : "—"}
          />
          <DetailRow
            label="Coordinates"
            value={
              incident.latitude
                ? `${incident.latitude.toFixed(5)}, ${incident.longitude.toFixed(5)}`
                : "Unknown"
            }
          />
        </div>
      </div>
    </div>
  );
}

function DetailRow({ label, value }) {
  return (
    <div style={styles.row}>
      <span style={styles.label}>{label}</span>
      <span style={styles.value}>{value}</span>
    </div>
  );
}

const styles = {
  overlay: {
    position: "fixed",
    inset: 0,
    backgroundColor: "rgba(0,0,0,0.6)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1000,
    backdropFilter: "blur(4px)",
  },
  panel: {
    backgroundColor: "#12121e",
    borderRadius: "12px",
    padding: "32px",
    maxWidth: "480px",
    width: "90%",
    border: "1px solid #1a1a2e",
    position: "relative",
    boxShadow: "0 24px 48px rgba(0,0,0,0.4)",
  },
  close: {
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
  category: {
    fontSize: "12px",
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "1px",
    marginBottom: "8px",
  },
  title: {
    fontSize: "20px",
    fontWeight: 700,
    color: "#f0f0f5",
    marginTop: 0,
    marginBottom: "24px",
    lineHeight: 1.3,
  },
  row: {
    display: "flex",
    justifyContent: "space-between",
    padding: "8px 0",
    borderBottom: "1px solid #1a1a2e",
  },
  label: { fontSize: "13px", color: "#5a5a7a" },
  value: { fontSize: "13px", color: "#e2e2e8", textAlign: "right", maxWidth: "60%" },
};
