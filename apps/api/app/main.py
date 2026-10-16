from fastapi import FastAPI

from app.core.http import configure_http
from app.features.ai.routes import router as ai_router
from app.features.analytics.routes import router as analytics_router
from app.features.audit.configuration_api import router as audit_configuration_router
from app.features.audit.routes import router as audit_router
from app.features.cases.routes import router as cases_router
from app.features.identity.routes import auth_router, organizations_router
from app.features.ingestion.routes import router as ingestion_router

app = FastAPI(title="ProcessMind AI API", version="0.1.0")
configure_http(app)
app.include_router(auth_router)
app.include_router(organizations_router)
app.include_router(ingestion_router)
app.include_router(audit_router)
app.include_router(audit_configuration_router)
app.include_router(ai_router)
app.include_router(cases_router)
app.include_router(analytics_router)
