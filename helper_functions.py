"""
CDR Assistant — FastAPI backend
Run: uvicorn main:app --reload --port 8000
"""
import logging
import sys
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from data import filter_incidents, get_incident_detail

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("cdr_assistant")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="CDR Assistant", version="1.0.0", docs_url="/docs")
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class FeedbackRequest(BaseModel):
    incident_id: str
    section: str
    rating: Optional[str] = None   # "up" | "down" | None
    comment: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes — UI
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    logger.info("GET / — serving main page")
    return templates.TemplateResponse("index.html", {"request": request})


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------
@app.get("/api/incidents")
async def list_incidents(search: str = "", status: str = "all"):
    logger.info("GET /api/incidents  search=%r  status=%r", search, status)
    results = filter_incidents(search=search, status=status)
    logger.info("  → returning %d incidents", len(results))
    return results


@app.get("/api/incidents/{incident_id}")
async def incident_detail(incident_id: str):
    logger.info("GET /api/incidents/%s", incident_id)
    detail = get_incident_detail(incident_id)
    if detail is None:
        logger.warning("  → incident %s not found", incident_id)
        raise HTTPException(status_code=404, detail=f"Incident {incident_id!r} not found")
    return detail


@app.post("/api/feedback")
async def submit_feedback(feedback: FeedbackRequest):
    snippet = (feedback.comment or "")[:80]
    logger.info(
        "POST /api/feedback  incident=%s  section=%r  rating=%s  comment=%r",
        feedback.incident_id,
        feedback.section,
        feedback.rating,
        snippet,
    )
    return {"success": True, "message": "Feedback recorded"}


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
