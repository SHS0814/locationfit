from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1 import agent, health, metadata, recommendations
from backend.app.core.config import settings
from backend.app.core.errors import (
    request_validation_error_handler,
    runtime_error_handler,
    value_error_handler,
    agent_state_error_handler,
    agent_timeout_error_handler,
    agent_unavailable_error_handler,
)
from backend.app.core.middleware import RecommendationRateLimitMiddleware, RequestContextMiddleware
from backend.app.services.recommender_service import RecommenderService
from backend.app.services.agent_service import (
    AgentStateError,
    AgentTimeoutError,
    AgentUnavailableError,
    LocationAgentService,
    OpenAIAgentRunner,
)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.recommender = RecommenderService(settings.artifact_dir)
        app.state.location_agent = LocationAgentService(
            app.state.recommender,
            OpenAIAgentRunner(model=settings.openai_model, max_turns=settings.agent_max_turns),
            timeout_seconds=settings.agent_timeout_seconds,
        )
        app.state.startup_error = None
    except Exception as exc:
        logger.exception("Failed to load recommendation artifacts")
        app.state.recommender = None
        app.state.location_agent = None
        app.state.startup_error = str(exc)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )
    app.add_middleware(
        RecommendationRateLimitMiddleware,
        limit=settings.rate_limit_per_minute,
        agent_limit=settings.agent_rate_limit_per_minute,
    )
    app.add_middleware(RequestContextMiddleware, max_request_bytes=settings.max_request_bytes)
    app.add_exception_handler(ValueError, value_error_handler)
    app.add_exception_handler(RuntimeError, runtime_error_handler)
    app.add_exception_handler(AgentUnavailableError, agent_unavailable_error_handler)
    app.add_exception_handler(AgentTimeoutError, agent_timeout_error_handler)
    app.add_exception_handler(AgentStateError, agent_state_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    for router in (health.router, metadata.router, recommendations.router, agent.router):
        app.include_router(router, prefix=settings.api_prefix)
    return app


app = create_app()
