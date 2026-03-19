import { useEffect, useRef } from "react";
import { MAPBOX_TOKEN, CATEGORY_COLORS } from "../constants.js";

export default function MapView({ incidents, center, onCenterChange, onIncidentSelect }) {
  const mapContainer = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef([]);

  const needsToken = MAPBOX_TOKEN === "__MAPBOX_TOKEN__";

  // Initialize Mapbox
  useEffect(() => {
    if (needsToken || !mapContainer.current || mapRef.current) return;

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
      map.on("click", (e) => onCenterChange({ lat: e.lngLat.lat, lng: e.lngLat.lng }));
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

    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    incidents.forEach((inc) => {
      if (!inc.latitude || !inc.longitude) return;

      const el = document.createElement("div");
      const color = inc.color_hex || CATEGORY_COLORS[inc.category] || "#9CA3AF";
      el.style.width = "10px";
      el.style.height = "10px";
      el.style.borderRadius = "50%";
      el.style.backgroundColor = color;
      el.style.border = "1.5px solid rgba(0,0,0,0.3)";
      el.style.cursor = "pointer";
      el.style.boxShadow = `0 0 6px ${color}44`;

      el.addEventListener("click", (e) => {
        e.stopPropagation();
        onIncidentSelect(inc);
      });

      const marker = new window.mapboxgl.Marker({ element: el })
        .setLngLat([inc.longitude, inc.latitude])
        .addTo(mapRef.current);

      markersRef.current.push(marker);
    });
  }, [incidents]);

  if (needsToken) {
    return (
      <div style={styles.placeholder}>
        <div style={styles.placeholderContent}>
          <h2 style={styles.placeholderTitle}>Map View</h2>
          <p style={styles.placeholderText}>
            Set <code>VITE_MAPBOX_TOKEN</code> in your <code>.env</code> to enable the map.
          </p>
          <p style={styles.placeholderText}>
            Get a free token at{" "}
            <a href="https://mapbox.com" target="_blank" rel="noreferrer" style={styles.link}>
              mapbox.com
            </a>
          </p>
          <p style={styles.placeholderSubtext}>
            Showing {incidents.length} incidents — switch to List view to browse them.
          </p>
        </div>
      </div>
    );
  }

  return <div ref={mapContainer} style={styles.map} />;
}

const styles = {
  map: { width: "100%", height: "100%" },
  placeholder: {
    width: "100%",
    height: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#0a0a14",
    backgroundImage: "radial-gradient(circle at 50% 50%, #1a1a2e 0%, #0a0a14 70%)",
  },
  placeholderContent: { textAlign: "center", maxWidth: "400px", padding: "40px" },
  placeholderTitle: { fontSize: "24px", fontWeight: 700, color: "#f0f0f5", marginBottom: "12px" },
  placeholderText: { fontSize: "14px", color: "#7c7c9a", lineHeight: 1.6, marginBottom: "8px" },
  placeholderSubtext: { fontSize: "13px", color: "#5a5a7a", marginTop: "20px" },
  link: { color: "#3B82F6", textDecoration: "none" },
};
