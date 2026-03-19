"""
CrimeMap API
=============
FastAPI backend for the CrimeMap crime data transparency platform.

Run locally:
    uvicorn backend.app.main:app --reload --port 8000

Or directly:
    python backend/app/main.py
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router

app = FastAPI(
    title="CrimeMap API",
    description="Crime data transparency platform — search and explore police incident data",
    version="0.1.0",
)

# CORS — allow frontend dev server and eventual production domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",    # Vite dev server
        "http://localhost:5173",    # Vite default
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
