from fastapi import FastAPI, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.engine import make_engine

app = FastAPI(title="ProcessMind AI API", version="0.1.0")


class Health(BaseModel):
    status: str


@app.get("/api/v1/health/live", response_model=Health)
def live() -> Health:
    return Health(status="ok")


@app.get("/api/v1/health/ready", response_model=Health)
def ready(response: Response) -> Health:
    try:
        with make_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = 503
        return Health(status="unavailable")
    return Health(status="ok")
