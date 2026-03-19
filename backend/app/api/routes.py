"""
CrimeMap API Routes
====================
All API endpoints for the CrimeMap platform.
"""

import math
from collections import Counter
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.app.api.deps import get_supabase
from backend.app.api.models import (
    AreaStats,
    CategoryGroup,
    CategoryInfo,
    DepartmentInfo,
    IncidentDetail,
    IncidentSummary,
    PaginatedResponse,
    SearchResponse,
)

router = APIRouter()


# ===========================================================================
# Search — the core map endpoint
# ===========================================================================

@router.get("/incidents/search", response_model=SearchResponse)
async def search_incidents(
    latitude: float = Query(..., description="Center latitude"),
    longitude: float = Query(..., description="Center longitude"),
    radius_miles: float = Query(default=1.0, ge=0.1, le=50.0),
    from_date: Optional[str] = Query(default=None, description="ISO date string"),
    to_date: Optional[str] = Query(default=None, description="ISO date string"),
    category: Optional[str] = Query(default=None, description="Top-level category filter"),
    limit: int = Query(default=500, ge=1, le=5000),
):
    """
    Search incidents within a radius of a point.
    Powers the map view.
    """
    supabase = get_supabase()

    params = {
        "search_lat": latitude,
        "search_lng": longitude,
        "radius_miles": radius_miles,
        "result_limit": limit,
    }

    if from_date:
        params["from_date"] = from_date
    if to_date:
        params["to_date"] = to_date
    if category:
        params["category_filter"] = category

    result = supabase.rpc("search_incidents_by_radius", params).execute()

    incidents = [
        IncidentSummary(
            id=str(row.get("incident_id", "")),
            incident_date=row.get("incident_date"),
            category=row.get("category"),
            subcategory=row.get("subcategory"),
            color_hex=row.get("color_hex"),
            description=row.get("description"),
            address=row.get("address_normalized"),
            city=row.get("city"),
            latitude=row.get("latitude"),
            longitude=row.get("longitude"),
            department_name=row.get("department_name"),
            distance_miles=round(row.get("distance_miles", 0), 3) if row.get("distance_miles") else None,
        )
        for row in result.data
    ]

    return SearchResponse(
        incidents=incidents,
        total=len(incidents),
        search_center={"latitude": latitude, "longitude": longitude},
        radius_miles=radius_miles,
    )


# ===========================================================================
# List — paginated incident list with filters
# ===========================================================================

@router.get("/incidents", response_model=PaginatedResponse)
async def list_incidents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    city: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    subcategory: Optional[str] = Query(default=None),
    from_date: Optional[str] = Query(default=None),
    to_date: Optional[str] = Query(default=None),
    sort_by: str = Query(default="incident_date", pattern="^(incident_date|category|city)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
):
    """
    Paginated list of incidents with filters.
    Powers the list view.
    """
    supabase = get_supabase()
    offset = (page - 1) * page_size

    # Build query
    query = supabase.table("incidents").select(
        "id, case_number, incident_date, description, source_category, "
        "address_normalized, city, state, latitude, longitude, "
        "category_id, incident_categories(category, subcategory, color_hex), "
        "departments(name)",
        count="exact",
    )

    # Apply filters
    if city:
        query = query.eq("city", city)
    if category:
        # Need to filter via category_id — look up matching IDs
        cat_result = supabase.table("incident_categories").select("id").eq("category", category).execute()
        cat_ids = [r["id"] for r in cat_result.data]
        if cat_ids:
            query = query.in_("category_id", cat_ids)
        else:
            return PaginatedResponse(
                incidents=[], total=0, page=page,
                page_size=page_size, total_pages=0,
            )
    if subcategory:
        cat_result = (
            supabase.table("incident_categories")
            .select("id")
            .eq("subcategory", subcategory)
            .execute()
        )
        cat_ids = [r["id"] for r in cat_result.data]
        if cat_ids:
            query = query.in_("category_id", cat_ids)
    if from_date:
        query = query.gte("incident_date", from_date)
    if to_date:
        query = query.lte("incident_date", to_date)

    # Sort and paginate
    desc = sort_order == "desc"
    query = query.order(sort_by, desc=desc).range(offset, offset + page_size - 1)

    result = query.execute()
    total = result.count if result.count is not None else 0

    incidents = []
    for row in result.data:
        cat_data = row.get("incident_categories") or {}
        dept_data = row.get("departments") or {}
        incidents.append(IncidentSummary(
            id=row["id"],
            case_number=row.get("case_number"),
            incident_date=row.get("incident_date"),
            category=cat_data.get("category"),
            subcategory=cat_data.get("subcategory"),
            color_hex=cat_data.get("color_hex"),
            description=row.get("description"),
            address=row.get("address_normalized"),
            city=row.get("city"),
            state=row.get("state"),
            latitude=row.get("latitude"),
            longitude=row.get("longitude"),
            department_name=dept_data.get("name"),
        ))

    return PaginatedResponse(
        incidents=incidents,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )


# ===========================================================================
# Incident Detail
# ===========================================================================

@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
async def get_incident(incident_id: str):
    """Get full details for a single incident."""
    supabase = get_supabase()

    result = (
        supabase.table("incidents")
        .select(
            "*, incident_categories(category, subcategory, color_hex, icon), "
            "departments(name, city)"
        )
        .eq("id", incident_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Incident not found")

    row = result.data[0]
    cat_data = row.get("incident_categories") or {}
    dept_data = row.get("departments") or {}

    return IncidentDetail(
        id=row["id"],
        case_number=row.get("case_number"),
        incident_date=row.get("incident_date"),
        reported_date=row.get("reported_date"),
        category=cat_data.get("category"),
        subcategory=cat_data.get("subcategory"),
        color_hex=cat_data.get("color_hex"),
        icon=cat_data.get("icon"),
        description=row.get("description"),
        source_category=row.get("source_category"),
        address_raw=row.get("address_raw"),
        address_normalized=row.get("address_normalized"),
        city=row.get("city"),
        state=row.get("state"),
        zip=row.get("zip"),
        latitude=row.get("latitude"),
        longitude=row.get("longitude"),
        is_geocoded=row.get("is_geocoded", False),
        geocode_quality=row.get("geocode_quality"),
        confidence_score=row.get("confidence_score"),
        department_name=dept_data.get("name"),
        department_city=dept_data.get("city"),
    )


# ===========================================================================
# Categories
# ===========================================================================

@router.get("/categories", response_model=list[CategoryGroup])
async def list_categories():
    """
    Get all categories grouped by top-level category.
    Powers the filter dropdowns in the UI.
    """
    supabase = get_supabase()

    result = supabase.table("incident_categories").select("*").order("category").order("subcategory").execute()

    groups = {}
    for row in result.data:
        cat = row["category"]
        if cat not in groups:
            groups[cat] = []
        groups[cat].append(CategoryInfo(
            id=row["id"],
            category=row["category"],
            subcategory=row["subcategory"],
            color_hex=row["color_hex"],
            icon=row.get("icon"),
            description=row.get("description"),
        ))

    return [
        CategoryGroup(category=cat, subcategories=subs)
        for cat, subs in sorted(groups.items())
    ]


# ===========================================================================
# Departments
# ===========================================================================

@router.get("/departments", response_model=list[DepartmentInfo])
async def list_departments():
    """Get all registered police departments."""
    supabase = get_supabase()

    result = supabase.table("departments").select("*").order("state").order("city").execute()

    departments = []
    for row in result.data:
        # Get incident count for this department
        count_result = (
            supabase.table("incidents")
            .select("id", count="exact")
            .eq("department_id", row["id"])
            .execute()
        )
        count = count_result.count if count_result.count is not None else 0

        departments.append(DepartmentInfo(
            id=row["id"],
            name=row["name"],
            city=row["city"],
            state=row["state"],
            website_url=row.get("website_url"),
            data_source_url=row.get("data_source_url"),
            data_format=row.get("data_format"),
            fetch_cadence=row.get("fetch_cadence"),
            is_active=row.get("is_active", True),
            incident_count=count,
        ))

    return departments


# ===========================================================================
# Stats — summary statistics for an area
# ===========================================================================

@router.get("/stats", response_model=AreaStats)
async def area_stats(
    latitude: float = Query(...),
    longitude: float = Query(...),
    radius_miles: float = Query(default=1.0, ge=0.1, le=50.0),
    from_date: Optional[str] = Query(default=None),
    to_date: Optional[str] = Query(default=None),
):
    """
    Get summary statistics for incidents in an area.
    Powers the insights/stats panel in the UI.
    """
    supabase = get_supabase()

    params = {
        "search_lat": latitude,
        "search_lng": longitude,
        "radius_miles": radius_miles,
        "result_limit": 5000,
    }
    if from_date:
        params["from_date"] = from_date
    if to_date:
        params["to_date"] = to_date

    result = supabase.rpc("search_incidents_by_radius", params).execute()
    data = result.data

    if not data:
        return AreaStats(
            total_incidents=0,
            date_range={"earliest": None, "latest": None},
            top_categories=[],
            incidents_by_month=[],
        )

    # Date range
    dates = [row["incident_date"] for row in data if row.get("incident_date")]
    earliest = min(dates) if dates else None
    latest = max(dates) if dates else None

    # Top categories
    cat_counts = Counter(
        (row.get("category", "Unknown"), row.get("subcategory", "Unknown"))
        for row in data
    )
    top_categories = [
        {"category": cat, "subcategory": sub, "count": count}
        for (cat, sub), count in cat_counts.most_common(15)
    ]

    # Incidents by month
    month_counts = Counter()
    for row in data:
        d = row.get("incident_date")
        if d:
            # Parse ISO date to extract year-month
            try:
                dt = datetime.fromisoformat(d.replace("Z", "+00:00")) if isinstance(d, str) else d
                month_key = dt.strftime("%Y-%m")
                month_counts[month_key] += 1
            except (ValueError, AttributeError):
                pass

    incidents_by_month = [
        {"month": month, "count": count}
        for month, count in sorted(month_counts.items())
    ]

    return AreaStats(
        total_incidents=len(data),
        date_range={"earliest": earliest, "latest": latest},
        top_categories=top_categories,
        incidents_by_month=incidents_by_month,
    )
