from fastapi import FastAPI

from app.core.config import settings
from app.core.http import configure_http
from app.features.ai.routes import router as ai_router
from app.features.analytics.routes import router as analytics_router
from app.features.audit.configuration_api import router as audit_configuration_router
from app.features.audit.routes import router as audit_router
from app.features.cases.routes import router as cases_router
from app.features.identity.routes import auth_router, organizations_router
from app.features.ingestion.routes import router as ingestion_router


def create_app() -> FastAPI:
    """Build business routes for the selected authorization boundary."""
    application = FastAPI(title="ProcessMind AI API", version="0.1.0")
    configure_http(application)
    # Shared-database routes remain available only for the documented rollback mode.
    if settings.business_auth_mode == "database":
        application.include_router(auth_router)
        application.include_router(organizations_router)
    application.include_router(ingestion_router)
    application.include_router(audit_router)
    application.include_router(audit_configuration_router)
    application.include_router(ai_router)
    application.include_router(cases_router)
    application.include_router(analytics_router)
    return application


app = create_app()
