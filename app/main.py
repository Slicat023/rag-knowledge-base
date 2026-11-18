"""FastAPI application entry point."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import chat as chat_api
from app.api import documents as documents_api
from app.api import system as system_api
from app.config import BASE_DIR, settings
from app.deps import registry
from app.services.embeddings import embedding_service
from app.services.llm import llm_factory
from app.services.parser import SUPPORTED_EXTENSIONS
from app.services.reranker import reranker

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def _warmup_models() -> None:
    logger.info("Warming up local models in the background ...")
    embedding_service.warmup()
    reranker.warmup()
    logger.info("Model warmup finished")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    recovered = registry.recover_interrupted()
    if recovered:
        logger.warning("Marked %d interrupted ingestion job(s) as failed", recovered)
    if settings.warmup_models:
        threading.Thread(target=_warmup_models, name="model-warmup", daemon=True).start()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
app.include_router(system_api.router)
app.include_router(documents_api.router)
app.include_router(chat_api.router)


def _page_context(active: str) -> dict:
    providers = llm_factory.info()
    default = settings.default_llm if settings.default_llm in providers else "qwen"
    if not providers.get(default, {}).get("configured"):
        configured = [name for name, info in providers.items() if info["configured"]]
        default = configured[0] if configured else default
    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "active": active,
        "default_llm": default,
        "providers": providers,
        "configured_count": len(settings.available_providers),
        "max_upload_mb": settings.max_upload_mb,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
    }


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def chat_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context=_page_context("chat"),
    )


@app.get("/knowledge", response_class=HTMLResponse, include_in_schema=False)
def knowledge_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="knowledge.html",
        context=_page_context("knowledge"),
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api", include_in_schema=False)
def api_root() -> dict:
    return {"app": settings.app_name, "version": settings.app_version, "docs": "/api/docs"}