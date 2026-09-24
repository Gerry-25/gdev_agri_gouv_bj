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

    lands = database["lands"]
    await lands.create_index("npi_owner")
    await lands.create_index([("department", 1), ("commune", 1)])
    await lands.create_index([("boundary", "2dsphere")])  # requêtes carte + détection de chevauchements
    await lands.create_index(
        "cadastral_reference",
        unique=True,
        partialFilterExpression={"cadastral_reference": {"$type": "string"}},
    )

    await database["disputes"].create_index([("land_ids", 1), ("status", 1)])
    await database["disputes"].create_index([("status", 1), ("created_at", -1)])
    await database["harvests"].create_index([("land_id", 1), ("season", 1), ("crop_type", 1)], unique=True)

    await database["market_offers"].create_index([("status", 1), ("created_at", -1)])
    await database["market_offers"].create_index("farmer_npi")

    alerts = database["phytosanitary_alerts"]
    await alerts.create_index([("health_status", 1), ("created_at", -1)])
    await alerts.create_index([("department", 1), ("commune", 1), ("created_at", -1)])
    await alerts.create_index([("farmer_npi", 1), ("created_at", -1)])
    await alerts.create_index([("location", "2dsphere")])

    await database["guides"].create_index("slug", unique=True)
    await database["guides"].create_index("category")
    # Les fichiers audio en cache expirent après 30 jours
    await database["audio_cache"].create_index("created_at", expireAfterSeconds=30 * 24 * 3600)


async def close_mongo_connection() -> None:
    if db.client:
        db.client.close()
        logger.info("Connexion MongoDB fermée.")


def get_database() -> AsyncIOMotorDatabase:
    return db.db
