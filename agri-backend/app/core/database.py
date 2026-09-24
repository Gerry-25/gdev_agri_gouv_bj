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
    await database["users"].create_index("role")
    await database["otp_codes"].create_index("npi", unique=True)
    await database["otp_codes"].create_index("expires_at", expireAfterSeconds=3600)
    await database["refresh_tokens"].create_index("token_hash", unique=True)
    await database["refresh_tokens"].create_index("npi")
    await database["refresh_tokens"].create_index("expires_at", expireAfterSeconds=0)

    lands = database["lands"]
    await lands.create_index("npi_owner")
    await lands.create_index([("department", 1), ("commune", 1)])
    await lands.create_index([("boundary", "2dsphere")])
    await lands.create_index("verification_status")  # requêtes carte + détection de chevauchements
    await lands.create_index(
        "cadastral_reference",
        unique=True,
        partialFilterExpression={"cadastral_reference": {"$type": "string"}},
    )

    await database["transfers"].create_index([("land_id", 1), ("status", 1)])
    await database["transfers"].create_index([("status", 1), ("created_at", -1)])
    await database["disputes"].create_index([("land_ids", 1), ("status", 1)])
    await database["disputes"].create_index([("status", 1), ("created_at", -1)])
    await database["harvests"].create_index([("land_id", 1), ("season", 1), ("crop_type", 1)], unique=True)

    await database["market_offers"].create_index([("status", 1), ("created_at", -1)])
    await database["market_offers"].create_index("farmer_npi")
    await database["market_offers"].create_index([("product_name", 1), ("department", 1)])
    await database["offer_interests"].create_index([("offer_id", 1), ("buyer_npi", 1)], unique=True)

    alerts = database["phytosanitary_alerts"]
    await alerts.create_index([("health_status", 1), ("observed_at", -1)])
    await alerts.create_index([("department", 1), ("commune", 1), ("observed_at", -1)])
    await alerts.create_index([("farmer_npi", 1), ("created_at", -1)])
    await alerts.create_index([("location", "2dsphere")])

    # Un même envoi hors ligne rejoué ne crée pas de doublon
    for coll, owner in (("lands", "npi_owner"), ("market_offers", "farmer_npi"), ("phytosanitary_alerts", "farmer_npi")):
        await database[coll].create_index(
            [(owner, 1), ("client_ref", 1)], unique=True,
            partialFilterExpression={"client_ref": {"$type": "string"}},
        )

    await database["notifications"].create_index([("npi", 1), ("read", 1), ("created_at", -1)])
    await database["notifications"].create_index("created_at", expireAfterSeconds=90 * 24 * 3600)

    # Domaine privé de l'État
    await database["state_domains"].create_index([("boundary", "2dsphere")])
    await database["state_domains"].create_index("status")
    await database["calls"].create_index([("domain_id", 1), ("status", 1)])
    await database["calls"].create_index([("status", 1), ("published_at", -1)])
    await database["applications"].create_index([("call_id", 1), ("farmer_npi", 1)], unique=True)
    await database["contestations"].create_index([("call_id", 1), ("npi", 1)], unique=True)
    await database["concessions"].create_index([("farmer_npi", 1), ("status", 1)])
    await database["concession_reports"].create_index([("concession_id", 1), ("season", 1), ("crop_type", 1)], unique=True)
    await database["concession_inspections"].create_index("concession_id")

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
