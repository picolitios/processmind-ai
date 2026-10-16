from fastapi import FastAPI

from app.core.http import configure_http
from app.features.identity.introspection import router as internal_router
from app.features.identity.routes import auth_router, organizations_router

app = FastAPI(title="ProcessMind AI Identity API", version="0.1.0")
configure_http(app, service_name="identity")
app.include_router(auth_router)
app.include_router(organizations_router)
app.include_router(internal_router)
