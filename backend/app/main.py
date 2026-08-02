from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.app.api.v1 import (
    agent,
    costs,
    finance,
    health,
    market,
    metadata,
    recommendations,
    research,
    security,
    stores,
)
from backend.app.core.ai_security import AIProtectionError, require_ai_session
from backend.app.core.config import settings
from backend.app.core.errors import (
    agent_state_error_handler,
    agent_timeout_error_handler,
    agent_unavailable_error_handler,
    ai_protection_error_handler,
    request_validation_error_handler,
    runtime_error_handler,
    store_data_unavailable_error_handler,
    store_upstream_error_handler,
    value_error_handler,
)
from backend.app.core.middleware import RecommendationRateLimitMiddleware, RequestContextMiddleware
from backend.app.services.agent_service import (
    AgentStateError,
    AgentTimeoutError,
    AgentUnavailableError,
    LocationAgentService,
    OpenAIAgentRunner,
)
from backend.app.services.cost_provider import (
    CommercialCostProvider,
    ParquetCommercialCostProvider,
    UnavailableCostProvider,
)
from backend.app.services.finance_service import FinancePlanService
from backend.app.services.recommender_service import RecommenderService
from backend.app.services.store_service import (
    CommercialStoreService,
    SbizStoreProvider,
    StoreDataUnavailableError,
    StoreUpstreamError,
)
from backend.app.services.web_research_service import OpenAIWebResearchRunner, WebResearchService
from backend.app.services.workspace_agent_service import (
    DatabaseFinancialCatalogProvider,
    OpenAIWorkspaceAgentRunner,
    WorkspaceAgentService,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        cost_provider: CommercialCostProvider
        try:
            cost_provider = ParquetCommercialCostProvider.from_artifact_dir(settings.artifact_dir)
        except (FileNotFoundError, RuntimeError) as exc:
            logger.warning("Commercial cost artifacts unavailable: %s", exc)
            cost_provider = UnavailableCostProvider()
        app.state.recommender = RecommenderService(settings.artifact_dir, cost_provider)
        app.state.store_service = CommercialStoreService(
            app.state.recommender,
            SbizStoreProvider(
                service_key=settings.data_go_kr_service_key,
                base_url=settings.sbiz_store_api_base_url,
                timeout_seconds=settings.store_api_timeout_seconds,
            ),
            cache_ttl_seconds=settings.store_cache_ttl_seconds,
            stale_ttl_seconds=settings.store_stale_ttl_seconds,
        )
        app.state.location_agent = LocationAgentService(
            app.state.recommender,
            OpenAIAgentRunner(model=settings.openai_model, max_turns=settings.agent_max_turns),
            timeout_seconds=settings.agent_timeout_seconds,
            cost_provider=cost_provider,
        )
        app.state.web_research_service = WebResearchService(
            app.state.recommender,
            app.state.store_service,
            OpenAIWebResearchRunner(model=settings.openai_model),
            timeout_seconds=settings.web_research_timeout_seconds,
        )
        app.state.finance_plan_service = FinancePlanService()
        app.state.workspace_agent = WorkspaceAgentService(
            OpenAIWorkspaceAgentRunner(model=settings.openai_model),
            store_service=app.state.store_service,
            web_research_service=app.state.web_research_service,
            finance_service=app.state.finance_plan_service,
            catalog_provider=DatabaseFinancialCatalogProvider(),
            timeout_seconds=settings.workspace_agent_timeout_seconds,
        )
        app.state.startup_error = None
    except Exception as exc:
        logger.exception("Failed to load recommendation artifacts")
        app.state.recommender = None
        app.state.location_agent = None
        app.state.workspace_agent = None
        app.state.store_service = None
        app.state.web_research_service = None
        app.state.finance_plan_service = None
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
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1_024)
    app.add_middleware(
        RecommendationRateLimitMiddleware,
        limit=settings.rate_limit_per_minute,
        agent_limit=settings.agent_rate_limit_per_minute,
        store_limit=settings.store_rate_limit_per_minute,
    )
    app.add_middleware(RequestContextMiddleware, max_request_bytes=settings.max_request_bytes)
    app.add_exception_handler(ValueError, value_error_handler)
    app.add_exception_handler(AIProtectionError, ai_protection_error_handler)
    app.add_exception_handler(RuntimeError, runtime_error_handler)
    app.add_exception_handler(AgentUnavailableError, agent_unavailable_error_handler)
    app.add_exception_handler(AgentTimeoutError, agent_timeout_error_handler)
    app.add_exception_handler(AgentStateError, agent_state_error_handler)
    app.add_exception_handler(StoreDataUnavailableError, store_data_unavailable_error_handler)
    app.add_exception_handler(StoreUpstreamError, store_upstream_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    for router in (health.router, security.router):
        app.include_router(router, prefix=settings.api_prefix)
    for router in (
        metadata.router,
        recommendations.router,
        market.router,
        costs.router,
        stores.router,
        agent.router,
        research.router,
        finance.router,
    ):
        app.include_router(
            router,
            prefix=settings.api_prefix,
            dependencies=[Depends(require_ai_session)],
        )
    return app


app = create_app()
