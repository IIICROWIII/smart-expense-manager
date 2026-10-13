"""Run locally with: python -m uvicorn backend.main:app --reload."""
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .database import Database
from .routes import router
from .services import ExpenseService
from .validation import NotFoundError, ValidationError

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "expenses.db"


def create_app(database_path=None):
    database = Database(database_path or os.getenv("EXPENSE_DB_PATH", str(DEFAULT_DB)))

    @asynccontextmanager
    async def lifespan(app):
        database.initialize()
        app.state.service = ExpenseService(database)
        yield

    app = FastAPI(title="Smart Expense Manager API", version="0.1.0", lifespan=lifespan,
                  description="Local, single-user expense tracking in TRY. Amount inputs are decimal strings; monetary outputs are integer cents.")
    origins = [value.strip() for value in os.getenv("EXPENSE_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://localhost:8501,http://127.0.0.1:5173").split(",") if value.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type"])

    @app.exception_handler(ValidationError)
    async def validation_error(request: Request, error: ValidationError):
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, error: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(sqlite3.Error)
    async def database_error(request: Request, error: sqlite3.Error):
        return JSONResponse(status_code=503, content={"detail": "Storage operation failed. Try again or check local database access."})

    app.include_router(router)
    frontend = Path(__file__).resolve().parent.parent / "frontend"
    if frontend.is_dir():
        app.mount("/assets", StaticFiles(directory=frontend), name="assets")

        @app.get("/", include_in_schema=False)
        def home():
            return FileResponse(frontend / "index.html")
    return app


app = create_app()
