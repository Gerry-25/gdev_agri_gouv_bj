"""Attribue un rôle à un utilisateur existant.

Usage (Docker) : docker compose exec api python -m app.scripts.promote_user <NPI> [state_agent|farmer|buyer]
"""
import asyncio
import sys

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.modules.auth.schemas import UserRole


async def main(npi: str, role: str) -> int:
    client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=5000)
    try:
        result = await client[settings.DATABASE_NAME]["users"].update_one({"npi": npi}, {"$set": {"role": role}})
    finally:
        client.close()
    if result.matched_count == 0:
        print(f"[!] Aucun utilisateur avec le NPI {npi}. Il doit d'abord se connecter une fois.")
        return 1
    print(f"[OK] {npi} a désormais le rôle '{role}'. Il doit se reconnecter pour obtenir un nouveau jeton.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    target_role = sys.argv[2] if len(sys.argv) > 2 else UserRole.STATE_AGENT.value
    if target_role not in {r.value for r in UserRole}:
        print(f"[!] Rôle invalide : {target_role}")
        sys.exit(1)
    sys.exit(asyncio.run(main(sys.argv[1], target_role)))
