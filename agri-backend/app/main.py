import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import close_mongo_connection, connect_to_mongo
from app.modules.auth.router import router as auth_router
from app.modules.lands.router import router as lands_router
from app.modules.market.router import router as market_router
from app.modules.monitoring.router import router as monitoring_router
from app.modules.state.router import router as state_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("agri")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    if not settings.gemini_enabled:
        logger.warning("GEMINI_API_KEY non configurée : le diagnostic IA fonctionne en mode simulation.")
    yield
    await close_mongo_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.1.0",
    description="Backend Monolithique Modulaire pour le Challenge Agriculture Intelligente",
    lifespan=lifespan,
)

origins = settings.cors_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    # Les navigateurs refusent les identifiants avec l'origine "*"
    allow_credentials="*" not in origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

for r in (auth_router, lands_router, monitoring_router, market_router, state_router):
    app.include_router(r, prefix=settings.API_V1_STR)


@app.get("/")
def health_check():
    return {"status": "online", "mode": "modular-monolith", "ai_mode": "gemini" if settings.gemini_enabled else "simulation"}
