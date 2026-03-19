# CrimeMap

A civic transparency platform that ingests police incident reports, normalizes them into a standardized taxonomy, and lets users search and explore incidents on a map or list.

## Current State

**Phase 1 (Complete):** Data foundation — Supabase + PostGIS database, ingestion pipeline for Boston PD, 252,370 incidents fully ingested with 100% geocoding coverage.

**Phase 2 (Complete):** FastAPI backend — 6 API endpoints (search by radius, paginated list, incident detail, categories, departments, area stats). All wired to the PostGIS `search_incidents_by_radius` function.

**Phase 3 (Complete):** React frontend — Vite + React app with Mapbox GL JS map, incident list view, filter sidebar (radius, category, date range), category breakdown, incident detail panel.

**Next up:** More MA departments (Worcester, Springfield, etc.), AI insights (Claude API), auth + Stripe paywall, React Native mobile app.

## Tech Stack

| Layer | Technology |
|---|---|
| Database | Supabase (PostgreSQL + PostGIS) |
| Backend | FastAPI (Python) |
| Ingestion | Python + httpx + Anthropic Claude API |
| Geocoding | Google Maps Geocoding API (with DB cache) |
| Frontend | React + Vite + Mapbox GL JS |
| Auth (later) | Supabase Auth |
| Payments (later) | Stripe |

## Project Structure

```
crimemap/
├── backend/
│   └── app/
│       ├── main.py              # FastAPI entry point
│       ├── config.py            # Pydantic settings from .env
│       ├── api/
│       │   ├── routes.py        # All API endpoints
│       │   ├── models.py        # Pydantic request/response schemas
│       │   └── deps.py          # Supabase client dependency
│       └── ingestion/
│           └── boston_pd.py     # Boston PD CSV ingestion pipeline
├── frontend/
│   ├── index.html
│   ├── main.jsx                 # React entry point + global styles
│   ├── App.jsx                  # Main app component (layout + state)
│   ├── api.js                   # fetchJSON helper + API_BASE
│   ├── constants.js             # BOSTON_CENTER, MAPBOX_TOKEN, CATEGORY_COLORS
│   └── components/
│       ├── Sidebar.jsx          # Filters, category breakdown, area stats
│       ├── MapView.jsx          # Mapbox GL JS map + markers
│       ├── ListView.jsx         # Paginated incident table
│       └── IncidentDetail.jsx   # Incident detail modal
├── database/
│   └── 001_initial_schema.sql   # Full schema migration
├── scripts/
│   ├── test_connections.py      # Verify all services
│   ├── verify_ingestion.py      # Check DB state post-ingestion
│   ├── remap_categories.py      # Re-map categories with Claude
│   └── geocode_backfill.py      # Backfill missing coordinates
├── .env                         # Secrets (not in git)
├── .env.example                 # Template for .env
├── .gitignore
├── requirements.txt             # Python dependencies
├── package.json                 # Node dependencies
└── vite.config.js               # Vite config with API proxy
```

## Database Schema

Core tables: `departments`, `ingestion_runs`, `raw_incidents`, `incidents`, `incident_categories`, `geocoding_cache`, `user_profiles`.

The `incidents` table has a PostGIS `geometry(Point, 4326)` column auto-populated by a trigger from `latitude`/`longitude`. The `search_incidents_by_radius` Postgres function powers spatial queries.

Key indexes: GIST on `location`, B-tree on `incident_date`, `category_id`, `department_id`.

## Environment Variables

Required in `.env` (see `.env.example`):
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `DATABASE_URL` (direct Postgres connection)
- `GOOGLE_MAPS_API_KEY`
- `ANTHROPIC_API_KEY`
- `VITE_MAPBOX_TOKEN` (for frontend map)

## Running Locally

Backend:
```
pip install -r requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

Frontend:
```
npm install
npm run dev
```

Frontend runs on `http://localhost:5173` with API proxy to `:8000`.

**WSL2 note:** Run `npm run dev` using WSL2-native Node.js (not Windows Node). Install via `nvm` inside Ubuntu if needed.

## Key Design Decisions

- **Two-layer ingestion:** Raw data → normalized incidents. Allows re-processing without re-fetching.
- **LLM category mapping:** Claude maps department-specific offense descriptions to our standardized taxonomy. Only unique values are sent (121 for Boston PD = 1 API call).
- **Geocoding cache:** Every address geocoded once, stored in `geocoding_cache` table. Saves significant Google API costs on repeat addresses.
- **PostGIS for spatial queries:** `ST_DWithin` with GIST index handles radius search at scale.
- **Supabase credentials:** Backend uses `SUPABASE_SERVICE_ROLE_KEY` (service role). `SUPABASE_ANON_KEY` is available for future client-side auth.

## Ingestion Pipeline Pattern

For each new department:
1. Register in `departments` table
2. Download raw data (CSV, PDF, API)
3. Extract unique offense descriptions
4. Send to Claude for category mapping (single API call)
5. Transform rows, geocode missing coords (with cache)
6. Batch insert into `incidents` table
7. PostGIS trigger auto-populates geometry

## Data Coverage

- **Boston PD:** 252,370 incidents (2023–Mar 2026), 100% geocoded
- **Target:** 20 largest MA cities, then national expansion

## Coding Conventions

- Python: Type hints, dataclasses, logging throughout
- API: FastAPI with Pydantic models, async endpoints
- Frontend: React functional components with hooks, inline styles (no CSS framework yet)
- SQL: Migrations numbered sequentially (001, 002, 003...)
- All secrets in `.env`, never hardcoded
