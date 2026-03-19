-- ============================================================================
-- CrimeMap: Initial Schema Migration
-- Run this in Supabase SQL Editor
-- Prerequisite: CREATE EXTENSION IF NOT EXISTS postgis;
-- ============================================================================

-- ============================================================================
-- 1. DEPARTMENTS
-- One row per police department we ingest data from
-- ============================================================================
CREATE TABLE departments (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL,
    city            text NOT NULL,
    state           text NOT NULL DEFAULT 'MA',
    website_url     text,
    data_source_url text,
    data_format     text CHECK (data_format IN ('csv', 'pdf', 'api', 'html', 'xlsx', 'other')),
    fetch_cadence   text CHECK (fetch_cadence IN ('daily', 'weekly', 'biweekly', 'monthly', 'unknown')),
    is_active       boolean NOT NULL DEFAULT true,
    notes           text,                          -- any quirks about this department's data
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX departments_state_city_idx ON departments (state, city);

-- ============================================================================
-- 2. INGESTION RUNS
-- Audit log of every fetch/parse attempt per department
-- ============================================================================
CREATE TABLE ingestion_runs (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    department_id       uuid NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    started_at          timestamptz NOT NULL DEFAULT now(),
    completed_at        timestamptz,
    status              text NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running', 'success', 'failed', 'partial')),
    records_found       integer DEFAULT 0,
    records_inserted    integer DEFAULT 0,
    records_skipped     integer DEFAULT 0,          -- duplicates or unparseable
    error_message       text,
    raw_file_path       text,                        -- path in Supabase Storage
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ingestion_runs_dept_idx ON ingestion_runs (department_id);
CREATE INDEX ingestion_runs_status_idx ON ingestion_runs (status);
CREATE INDEX ingestion_runs_started_idx ON ingestion_runs (started_at DESC);

-- ============================================================================
-- 3. INCIDENT CATEGORIES
-- Our standardized taxonomy that all department-specific types map to
-- ============================================================================
CREATE TABLE incident_categories (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    category        text NOT NULL,                   -- e.g. 'Violent Crime'
    subcategory     text NOT NULL,                   -- e.g. 'Assault'
    description     text,
    color_hex       text NOT NULL DEFAULT '#6B7280', -- for map pins
    icon            text,                            -- icon name for UI
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (category, subcategory)
);

-- ============================================================================
-- 4. RAW INCIDENTS (staging layer)
-- Stores exactly what was parsed from the source, before normalization
-- ============================================================================
CREATE TABLE raw_incidents (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_run_id        uuid NOT NULL REFERENCES ingestion_runs(id) ON DELETE CASCADE,
    department_id           uuid NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    raw_data                jsonb NOT NULL,           -- the original row/record as-is
    parse_confidence        float,                    -- LLM confidence 0.0-1.0
    normalization_status    text NOT NULL DEFAULT 'pending'
                            CHECK (normalization_status IN ('pending', 'normalized', 'failed', 'flagged')),
    error_message           text,
    created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX raw_incidents_run_idx ON raw_incidents (ingestion_run_id);
CREATE INDEX raw_incidents_dept_idx ON raw_incidents (department_id);
CREATE INDEX raw_incidents_status_idx ON raw_incidents (normalization_status);

-- ============================================================================
-- 5. INCIDENTS (normalized, queryable — the core table)
-- This is what end users search against
-- ============================================================================
CREATE TABLE incidents (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_incident_id     uuid REFERENCES raw_incidents(id) ON DELETE SET NULL,
    department_id       uuid NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    category_id         uuid REFERENCES incident_categories(id),

    -- Standardized fields
    incident_date       timestamptz,
    reported_date       timestamptz,
    description         text,
    case_number         text,

    -- Location
    address_raw         text,                        -- original address from source
    address_normalized  text,                        -- cleaned/geocoded address
    city                text,
    state               text NOT NULL DEFAULT 'MA',
    zip                 text,
    latitude            float,
    longitude           float,
    location            geometry(Point, 4326),       -- PostGIS geospatial column

    -- Department's own categorization (preserved for reference)
    source_category     text,

    -- Quality metadata
    confidence_score    float,                       -- LLM normalization confidence
    is_geocoded         boolean NOT NULL DEFAULT false,
    geocode_quality     text,                        -- 'rooftop', 'range', 'approximate', 'failed'

    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    -- Prevent duplicate incidents from same department
    UNIQUE (department_id, case_number)
);

-- The critical indexes for query performance
CREATE INDEX incidents_location_gist_idx ON incidents USING GIST (location);
CREATE INDEX incidents_date_idx ON incidents (incident_date DESC);
CREATE INDEX incidents_category_idx ON incidents (category_id);
CREATE INDEX incidents_dept_idx ON incidents (department_id);
CREATE INDEX incidents_city_idx ON incidents (city);

-- Composite: the most common user query (recent incidents in an area)
CREATE INDEX incidents_location_recent_idx ON incidents USING GIST (location)
    WHERE incident_date > now() - INTERVAL '1 year';

-- For duplicate detection during ingestion
CREATE INDEX incidents_case_number_idx ON incidents (department_id, case_number);

-- ============================================================================
-- 6. GEOCODING CACHE
-- Cache every address we geocode so we never pay twice for the same lookup
-- ============================================================================
CREATE TABLE geocoding_cache (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    address_input       text NOT NULL,               -- the raw address string we sent
    address_normalized  text,                        -- what Google returned as formatted address
    latitude            float,
    longitude           float,
    location            geometry(Point, 4326),
    quality             text,                        -- 'rooftop', 'range_interpolated', 'geometric_center', 'approximate'
    provider            text NOT NULL DEFAULT 'google', -- in case we switch providers later
    raw_response        jsonb,                       -- full API response for debugging
    created_at          timestamptz NOT NULL DEFAULT now(),

    -- One cache entry per unique input string
    UNIQUE (address_input)
);

CREATE INDEX geocoding_cache_address_idx ON geocoding_cache (address_input);
CREATE INDEX geocoding_cache_location_idx ON geocoding_cache USING GIST (location);

-- ============================================================================
-- 7. USERS (extends Supabase Auth)
-- ============================================================================
CREATE TABLE user_profiles (
    id                  uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email               text,
    display_name        text,
    query_count         integer NOT NULL DEFAULT 0,
    last_reset_at       timestamptz NOT NULL DEFAULT now(),
    subscription_tier   text NOT NULL DEFAULT 'free'
                        CHECK (subscription_tier IN ('free', 'paid', 'admin')),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- 8. ROW LEVEL SECURITY POLICIES
-- Enable RLS on all tables; service role (backend) gets full access
-- User-facing restrictions will be added when we build auth
-- ============================================================================

ALTER TABLE departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE raw_incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE geocoding_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

-- Service role bypass (your backend uses the service_role key)
-- These allow your FastAPI backend full access to everything
CREATE POLICY "Service role full access" ON departments FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON ingestion_runs FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON raw_incidents FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON incidents FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON incident_categories FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON geocoding_cache FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON user_profiles FOR ALL USING (true) WITH CHECK (true);

-- Public read access to incidents and categories (anyone can search)
CREATE POLICY "Public read incidents" ON incidents FOR SELECT USING (true);
CREATE POLICY "Public read categories" ON incident_categories FOR SELECT USING (true);
CREATE POLICY "Public read departments" ON departments FOR SELECT USING (true);

-- ============================================================================
-- 9. AUTO-UPDATE TIMESTAMPS
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER departments_updated_at
    BEFORE UPDATE ON departments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER incidents_updated_at
    BEFORE UPDATE ON incidents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER user_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- 10. SEED DATA: Standardized Incident Categories
-- ============================================================================
INSERT INTO incident_categories (category, subcategory, color_hex, icon) VALUES
    -- Violent Crime (red tones)
    ('Violent Crime',   'Homicide',             '#DC2626', 'alert-triangle'),
    ('Violent Crime',   'Assault',              '#EF4444', 'alert-triangle'),
    ('Violent Crime',   'Robbery',              '#F87171', 'alert-triangle'),
    ('Violent Crime',   'Sexual Assault',       '#DC2626', 'alert-triangle'),
    ('Violent Crime',   'Kidnapping',           '#B91C1C', 'alert-triangle'),
    ('Violent Crime',   'Domestic Violence',    '#DC2626', 'alert-triangle'),

    -- Property Crime (orange tones)
    ('Property Crime',  'Burglary',             '#EA580C', 'home'),
    ('Property Crime',  'Theft',                '#F97316', 'shopping-bag'),
    ('Property Crime',  'Motor Vehicle Theft',  '#FB923C', 'car'),
    ('Property Crime',  'Arson',                '#C2410C', 'flame'),
    ('Property Crime',  'Vandalism',            '#FDBA74', 'edit'),

    -- Drug Offenses (purple tones)
    ('Drug Offenses',   'Possession',           '#7C3AED', 'package'),
    ('Drug Offenses',   'Distribution',         '#6D28D9', 'package'),
    ('Drug Offenses',   'Manufacturing',        '#5B21B6', 'package'),

    -- Traffic (blue tones)
    ('Traffic',         'DUI/OUI',              '#2563EB', 'navigation'),
    ('Traffic',         'Hit and Run',          '#3B82F6', 'navigation'),
    ('Traffic',         'Accident',             '#60A5FA', 'navigation'),
    ('Traffic',         'Traffic Violation',    '#93C5FD', 'navigation'),

    -- Disturbance (yellow tones)
    ('Disturbance',     'Noise Complaint',      '#CA8A04', 'volume-2'),
    ('Disturbance',     'Trespassing',          '#EAB308', 'alert-circle'),
    ('Disturbance',     'Disorderly Conduct',   '#FACC15', 'alert-circle'),
    ('Disturbance',     'Harassment',           '#FDE047', 'alert-circle'),

    -- Fraud & Financial (green tones)
    ('Fraud',           'Identity Theft',       '#059669', 'credit-card'),
    ('Fraud',           'Fraud',                '#10B981', 'credit-card'),
    ('Fraud',           'Forgery',              '#34D399', 'credit-card'),
    ('Fraud',           'Embezzlement',         '#6EE7B7', 'credit-card'),

    -- Weapons (dark red)
    ('Weapons',         'Illegal Possession',   '#991B1B', 'shield'),
    ('Weapons',         'Discharge',            '#7F1D1D', 'shield'),

    -- Other (gray tones)
    ('Other',           'Missing Person',       '#4B5563', 'search'),
    ('Other',           'Warrant',              '#6B7280', 'file-text'),
    ('Other',           'Suspicious Activity',  '#9CA3AF', 'eye'),
    ('Other',           'Animal Complaint',     '#D1D5DB', 'heart'),
    ('Other',           'Other',                '#E5E7EB', 'help-circle');

-- ============================================================================
-- 11. HELPER FUNCTION: Search incidents within a radius
-- This is the core query your API will use for map searches
-- ============================================================================
CREATE OR REPLACE FUNCTION search_incidents_by_radius(
    search_lat float,
    search_lng float,
    radius_miles float DEFAULT 1.0,
    from_date timestamptz DEFAULT NULL,
    to_date timestamptz DEFAULT NULL,
    category_filter text DEFAULT NULL,
    result_limit integer DEFAULT 500
)
RETURNS TABLE (
    incident_id uuid,
    incident_date timestamptz,
    category text,
    subcategory text,
    description text,
    address_normalized text,
    city text,
    latitude float,
    longitude float,
    distance_miles float,
    color_hex text,
    department_name text
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        i.id AS incident_id,
        i.incident_date,
        ic.category,
        ic.subcategory,
        i.description,
        i.address_normalized,
        i.city,
        i.latitude,
        i.longitude,
        (ST_Distance(
            i.location::geography,
            ST_SetSRID(ST_MakePoint(search_lng, search_lat), 4326)::geography
        ) / 1609.344)::float AS distance_miles,
        ic.color_hex,
        d.name AS department_name
    FROM incidents i
    LEFT JOIN incident_categories ic ON i.category_id = ic.id
    LEFT JOIN departments d ON i.department_id = d.id
    WHERE
        i.location IS NOT NULL
        AND ST_DWithin(
            i.location::geography,
            ST_SetSRID(ST_MakePoint(search_lng, search_lat), 4326)::geography,
            radius_miles * 1609.344  -- convert miles to meters
        )
        AND (from_date IS NULL OR i.incident_date >= from_date)
        AND (to_date IS NULL OR i.incident_date <= to_date)
        AND (category_filter IS NULL OR ic.category = category_filter)
    ORDER BY i.incident_date DESC
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;
