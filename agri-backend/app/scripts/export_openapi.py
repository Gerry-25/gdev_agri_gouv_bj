"""Exporte le contrat OpenAPI (utilisé pour générer le client TypeScript du frontend).

Usage : python -m app.scripts.export_openapi > ../agri-frontend/openapi.json
"""
import json
import os
import sys

# L'export n'a besoin ni de la base ni de secrets réels
os.environ.setdefault("MONGODB_URL", "mongodb://export")
os.environ.setdefault("JWT_SECRET_KEY", "export-" + "x" * 40)

from app.main import app  # noqa: E402

json.dump(app.openapi(), sys.stdout, ensure_ascii=False, indent=1)
