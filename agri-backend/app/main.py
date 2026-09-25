import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import close_mongo_connection, connect_to_mongo, get_database
from app.modules.agronomy.router import router as agronomy_router
from app.modules.assistant.router import router as assistant_router
from app.modules.auth.router import router as auth_router
from app.modules.domains.planning import router as planning_router
from app.modules.insights.router import router as insights_router
from app.modules.storage.router import router as storage_router
from app.modules.domains.router import router as domains_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.knowledge.seed import seed_guides
from app.modules.lands.router import router as lands_router
from app.modules.market.router import router as market_router
from app.modules.monitoring.router import router as monitoring_router
from app.modules.notifications.router import router as notifications_router
from app.modules.performance.router import router as performance_router
from app.modules.state.router import router as state_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("agri")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    if n := await seed_guides(get_database()):
        logger.info("%d fiche(s) pratique(s) d'exemple ajoutée(s).", n)
    if settings.SMS_PROVIDER == "simulation":
        logger.warning("SMS en mode simulation : le code de connexion est renvoyé dans la réponse de l'API.")
    if not settings.gemini_enabled:
        logger.warning("GEMINI_API_KEY non configurée : diagnostic IA en mode simulation, lecture audio désactivée.")
    yield
    await close_mongo_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="4.1.0",
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

# Ordre important : les routes fixes (/domains/plans/..., /lands/disputes/...) avant les routes à paramètre
for r in (auth_router, insights_router, agronomy_router, lands_router, monitoring_router, market_router, state_router,
          knowledge_router, notifications_router, performance_router, planning_router, domains_router, assistant_router,
          storage_router):
    app.include_router(r, prefix=settings.API_V1_STR)


@app.get("/")
def health_check():
    return {"status": "online", "mode": "modular-monolith", "ai_mode": "gemini" if settings.gemini_enabled else "simulation"}


@app.get("/health", summary="État de l'API et de la base de données")
async def health():
    try:
        await get_database().client.admin.command("ping")
    except Exception:
        raise HTTPException(status_code=503, detail="Base de données injoignable.")
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "ai_mode": "gemini" if settings.gemini_enabled else "simulation",
        "sms_mode": settings.SMS_PROVIDER,
    }
