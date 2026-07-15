from fastapi import FastAPI, Request

from app.api.health import router as health_router
from app.api.evidence_graph import router as evidence_graph_router
from app.api.qa import router as qa_router
from app.api.report import router as report_router
from app.api.verification import router as verification_router
from app.core.config import settings


app = FastAPI(title=settings.service_name, version="0.1.0")


@app.middleware("http")
async def expose_llm_provider(request: Request, call_next):
    """Expose the active provider without changing response JSON contracts."""
    response = await call_next(request)
    response.headers["X-AI-Provider"] = settings.llm_provider.strip().lower()
    return response


app.include_router(health_router)
app.include_router(qa_router)
app.include_router(report_router)
app.include_router(verification_router)
app.include_router(evidence_graph_router)
