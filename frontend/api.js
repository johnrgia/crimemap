// API base — uses Vite's proxy (/api → http://localhost:8000)
export const API_BASE = "/api/v1";

export async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}
