from fastapi import APIRouter

from app.core.providers.factory import get_provider
from app.core.settings import settings

router = APIRouter(prefix="", tags=["health"])


@router.get("/health")
async def health() -> dict:
    provider = get_provider()
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "provider": provider.name,
    }


@router.get("/health/provider")
async def provider_health() -> dict:
    provider = get_provider()
    diagnostics = await provider.diagnose()
    return {
        "status": "ok",
        "provider": provider.name,
        "configured": provider.configured,
        "supports_stream": provider.supports_stream,
        "base_url": provider.base_url,
        "model": provider.model,
        "transport": provider.transport,
        "reachable": diagnostics["reachable"],
        "tag_reachable": diagnostics.get("tag_reachable", diagnostics["reachable"]),
        "generation_reachable": diagnostics.get("generation_reachable", diagnostics["reachable"]),
        "last_error": diagnostics["last_error"],
    }
