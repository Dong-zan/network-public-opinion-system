from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.qa import router as qa_router
from app.api.report import router as report_router
from app.core.config import settings


app = FastAPI(title=settings.service_name, version="0.1.0")
app.include_router(health_router)
app.include_router(qa_router)
app.include_router(report_router)
