"""Fiches d'exemple insérées au premier démarrage.

ATTENTION : contenu indicatif (verified=False), à faire valider et compléter par le Ministère de
l'Agriculture, de l'Élevage et de la Pêche (MAEP) ou les services habilités avant toute diffusion.
"""
from app.core.utils import utcnow

_SOURCE = "Exemple à faire valider par le MAEP / les services habilités"

SEED_GUIDES = [
    {
        "slug": "reconnaitre-pesticide-autorise",
        "title": "Reconnaître un pesticide autorisé",
        "category": "produits_interdits",
        "summary": "N'achetez que des produits homologués, vendus fermés, avec une étiquette complète. Refusez les produits sans étiquette ou reconditionnés.",
        "steps": [
            "Achetez chez un distributeur agréé.",
            "Vérifiez que l'emballage est d'origine et bien fermé.",
            "L'étiquette doit indiquer le nom du produit, la matière active, la dose et le délai avant récolte.",
            "Refusez les produits vendus au détail dans des bouteilles ou sachets réutilisés.",
            "En cas de doute, demandez conseil à l'agent de vulgarisation.",
        ],
        "content": (
            "Certaines matières actives sont interdites au niveau international, par exemple l'endosulfan, "
            "inscrit à la Convention de Stockholm sur les polluants organiques persistants.\n\n"
            "**À compléter** : liste officielle des produits homologués et interdits au Bénin."
        ),
        "pictogram": "forbidden",
        "source": _SOURCE,
    },
    {
        "slug": "delai-avant-recolte",
        "title": "Respecter le délai avant récolte",
        "category": "normes_sanitaires",
        "summary": "Après un traitement, attendez le nombre de jours écrit sur l'étiquette avant de récolter ou de vendre.",
        "steps": [
            "Lisez le délai avant récolte (DAR) sur l'étiquette.",
            "Notez la date du traitement.",
            "Ne récoltez pas et ne vendez pas avant la fin du délai.",
            "Prévenez l'acheteur si un traitement a été fait récemment.",
        ],
        "content": "Des résidus de pesticides trop élevés sont dangereux pour les consommateurs et peuvent bloquer la vente, notamment à l'export.",
        "pictogram": "calendar",
        "source": _SOURCE,
    },
    {
        "slug": "se-proteger-pendant-traitement",
        "title": "Se protéger pendant un traitement",
        "category": "bonnes_pratiques",
        "summary": "Portez gants, masque, bottes et habits couvrants. Ne traitez pas par vent fort, et lavez-vous après.",
        "steps": [
            "Portez gants, masque, lunettes, bottes et manches longues.",
            "Ne traitez pas s'il y a du vent ou si la pluie arrive.",
            "Ne mangez pas, ne buvez pas et ne fumez pas pendant le traitement.",
            "Lavez-vous et lavez vos habits après.",
            "Gardez les produits loin des enfants et de la nourriture.",
            "Ne réutilisez jamais un emballage vide pour l'eau ou la nourriture.",
        ],
        "pictogram": "shield",
        "source": _SOURCE,
    },
    {
        "slug": "extrait-feuilles-neem",
        "title": "Préparer un extrait de feuilles de neem",
        "category": "bonnes_pratiques",
        "summary": "Le neem est un insecticide naturel. On pile des feuilles, on les laisse tremper dans l'eau, on filtre et on pulvérise le soir.",
        "steps": [
            "Piler des feuilles fraîches de neem.",
            "Les laisser tremper une nuit dans de l'eau propre.",
            "Filtrer avec un tissu.",
            "Pulvériser le soir, sur le dessus et le dessous des feuilles.",
            "Recommencer après une pluie.",
        ],
        "content": "**À compléter** : quantités et fréquence recommandées par les services de vulgarisation.",
        "pictogram": "leaf",
        "crops": ["Maïs", "Tomate", "Niébé", "Chou"],
        "source": _SOURCE,
    },
    {
        "slug": "declarer-litige-foncier",
        "title": "Que faire en cas de litige sur une parcelle ?",
        "category": "reglementation",
        "summary": "Signalez le litige dans l'application, gardez vos papiers, et rapprochez-vous de la mairie ou des services du foncier.",
        "steps": [
            "Signalez le litige depuis la fiche de la parcelle.",
            "Rassemblez vos documents : attestation, acte de vente, témoins.",
            "Privilégiez d'abord le dialogue ou la médiation locale.",
            "Contactez la mairie ou l'Agence Nationale du Domaine et du Foncier (ANDF).",
        ],
        "content": "**À compléter** : procédures officielles et textes de loi applicables.",
        "pictogram": "law",
        "source": _SOURCE,
    },
    {
        "slug": "enregistrer-parcelle-gps",
        "title": "Comment enregistrer ma parcelle avec le GPS ?",
        "category": "faq",
        "summary": "Activez le GPS, puis faites le tour de votre champ à pied en ajoutant un point à chaque coin ou changement de direction.",
        "steps": [
            "Activez la localisation du téléphone, à découvert.",
            "Placez-vous à un coin du champ et ajoutez le premier point.",
            "Marchez le long de la bordure et ajoutez un point à chaque changement de direction.",
            "Revenez au point de départ, puis validez.",
            "Vérifiez la forme de la parcelle sur la carte.",
        ],
        "pictogram": "map",
        "source": "Mode d'emploi AgriSmart",
        "verified": True,
    },
]


async def seed_guides(db) -> int:
    """Insère les fiches absentes, sans jamais écraser une fiche existante."""
    inserted = 0
    for guide in SEED_GUIDES:
        doc = {"content": "", "crops": [], "verified": False, "source_url": None, **guide,
               "updated_at": utcnow(), "updated_by": "seed"}
        res = await db["guides"].update_one({"slug": guide["slug"]}, {"$setOnInsert": doc}, upsert=True)
        inserted += 1 if res.upserted_id else 0
    return inserted
