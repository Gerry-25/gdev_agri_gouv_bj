import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)


class Database:
    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None


db = Database()


async def connect_to_mongo() -> None:
    db.client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=5000, tz_aware=True)
    db.db = db.client[settings.DATABASE_NAME]
    await db.client.admin.command("ping")
    await create_indexes(db.db)
    logger.info("Connecté à MongoDB : %s", settings.DATABASE_NAME)


async def create_indexes(database: AsyncIOMotorDatabase) -> None:
    await database["users"].create_index("npi", unique=True)
    await database["lands"].create_index("npi_owner")
    # Unicité de la référence cadastrale uniquement quand elle est renseignée
    await database["lands"].create_index(
        "cadastral_reference",
        unique=True,
        partialFilterExpression={"cadastral_reference": {"$type": "string"}},
    )
    await database["market_offers"].create_index([("status", 1), ("created_at", -1)])
    await database["market_offers"].create_index("farmer_npi")
    await database["phytosanitary_alerts"].create_index([("health_status", 1), ("created_at", -1)])


async def close_mongo_connection() -> None:
    if db.client:
        db.client.close()
        logger.info("Connexion MongoDB fermée.")


def get_database() -> AsyncIOMotorDatabase:
    return db.db
