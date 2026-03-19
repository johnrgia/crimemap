"""
Pydantic models for API request/response schemas.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ===========================================================================
# Incidents
# ===========================================================================

class IncidentSummary(BaseModel):
    """Incident as returned in search results and list views."""
    id: str
    case_number: Optional[str] = None
    incident_date: Optional[datetime] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    color_hex: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    department_name: Optional[str] = None
    distance_miles: Optional[float] = None


class IncidentDetail(BaseModel):
    """Full incident detail for single-incident view."""
    id: str
    case_number: Optional[str] = None
    incident_date: Optional[datetime] = None
    reported_date: Optional[datetime] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    color_hex: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    source_category: Optional[str] = None
    address_raw: Optional[str] = None
    address_normalized: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_geocoded: bool = False
    geocode_quality: Optional[str] = None
    confidence_score: Optional[float] = None
    department_name: Optional[str] = None
    department_city: Optional[str] = None


# ===========================================================================
# Search
# ===========================================================================

class SearchRequest(BaseModel):
    """Parameters for searching incidents by location."""
    latitude: float = Field(..., description="Center latitude for radius search")
    longitude: float = Field(..., description="Center longitude for radius search")
    radius_miles: float = Field(default=1.0, ge=0.1, le=50.0, description="Search radius in miles")
    from_date: Optional[datetime] = Field(default=None, description="Start date filter")
    to_date: Optional[datetime] = Field(default=None, description="End date filter")
    category: Optional[str] = Field(default=None, description="Filter by top-level category")
    limit: int = Field(default=500, ge=1, le=5000, description="Max results")


class SearchResponse(BaseModel):
    """Response for a search query."""
    incidents: list[IncidentSummary]
    total: int
    search_center: dict  # {latitude, longitude}
    radius_miles: float


# ===========================================================================
# List / Pagination
# ===========================================================================

class IncidentListRequest(BaseModel):
    """Parameters for paginated incident list."""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)
    city: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    sort_by: str = Field(default="incident_date", pattern="^(incident_date|category|city)$")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")


class PaginatedResponse(BaseModel):
    """Paginated list response."""
    incidents: list[IncidentSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


# ===========================================================================
# Categories
# ===========================================================================

class CategoryInfo(BaseModel):
    """A single category/subcategory."""
    id: str
    category: str
    subcategory: str
    color_hex: str
    icon: Optional[str] = None
    description: Optional[str] = None


class CategoryGroup(BaseModel):
    """A top-level category with its subcategories."""
    category: str
    subcategories: list[CategoryInfo]
    incident_count: Optional[int] = None


# ===========================================================================
# Departments
# ===========================================================================

class DepartmentInfo(BaseModel):
    """Police department metadata."""
    id: str
    name: str
    city: str
    state: str
    website_url: Optional[str] = None
    data_source_url: Optional[str] = None
    data_format: Optional[str] = None
    fetch_cadence: Optional[str] = None
    is_active: bool
    incident_count: Optional[int] = None


# ===========================================================================
# Stats
# ===========================================================================

class AreaStats(BaseModel):
    """Summary statistics for an area."""
    total_incidents: int
    date_range: dict  # {earliest, latest}
    top_categories: list[dict]  # [{category, subcategory, count}, ...]
    incidents_by_month: list[dict]  # [{month, count}, ...]
