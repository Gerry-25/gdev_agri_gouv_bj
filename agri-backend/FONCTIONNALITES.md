# AgriSmart Bénin : fonctionnalités de la plateforme

> Document de référence tenu à jour à chaque ajout ou modification.
> **Version backend : 3.1.0**, dernière mise à jour : 24/09/2026.
> Détails techniques et routes : voir `README.md`.

## Sommaire

1. [Authentification et profils](#1-authentification-et-profils)
2. [Foncier, parcelles et rendements](#2-foncier-parcelles-et-rendements)
3. [Monitoring et diagnostic phytosanitaire](#3-monitoring-et-diagnostic-phytosanitaire)
4. [Marché agricole](#4-marché-agricole)
5. [Supervision de l'État](#5-supervision-de-létat)
6. [Domaine privé de l'État et performance](#6-domaine-privé-de-létat-et-performance)
7. [Information et réglementation](#7-information-et-réglementation)
8. [Fonctions transverses](#8-fonctions-transverses)
9. [Points en attente](#9-points-en-attente)
10. [Historique des modifications](#10-historique-des-modifications)

## 1. Authentification et profils

- **Connexion par NPI et code SMS.** L'utilisateur saisit son NPI et son téléphone, puis le code reçu. En attendant un vrai fournisseur SMS, le code est renvoyé par l'API pour être affiché à l'écran.
- **Protection anti-abus.** Un code par minute, cinq par heure, cinq essais par code. Le mode simulation est interdit en production.
- **Session longue.** Le jeton d'accès dure 1 heure et se renouvelle automatiquement pendant 30 jours. On peut se déconnecter d'un appareil ou de tous.
- **Rôles.** Exploitant, acheteur, agent de l'État et superviseur. Les rôles de l'État ne s'attribuent que par un administrateur.
- **Profil modifiable.** Nom, langue préférée (français, fon, yoruba, anglais), département et commune.

## 2. Foncier, parcelles et rendements

- **Parcelles par contour GPS.** L'exploitant fait le tour de son champ. Le serveur valide la forme et vérifie que les points sont au Bénin. Il calcule lui-même la surface, le périmètre et le centre.
- **Prévention des litiges.**
  - Un chevauchement avec la parcelle d'un autre exploitant ou avec une terre de l'État ouvre automatiquement un litige.
  - Un tiers peut aussi signaler un litige.
  - Les agents le traitent : médiation, résolution ou rejet.
- **Traçabilité.** Les anciens contours et les propriétaires successifs sont conservés.
- **Vérification.** Un agent contrôle la parcelle sur le terrain et la valide. Tout changement de contour oblige à revérifier.
- **Transferts de propriété.** Vente, héritage ou donation : le propriétaire demande, un agent valide.
- **Production.** Les rendements prévus par parcelle et les récoltes réelles sont suivis par saison.
- **Cartographie.** Les parcelles sont exportées en GeoJSON, prêt pour Leaflet ou MapLibre.

## 3. Monitoring et diagnostic phytosanitaire

- **Diagnostic photo par Gemini.** L'IA identifie la culture, la maladie ou le ravageur, et la gravité, avec un code couleur.
- **Conseils adaptés.**
  - Un résumé très simple, dans la langue choisie.
  - Des étapes de traitement courtes, en privilégiant les solutions locales comme le neem.
  - Jamais de produit interdit.
- **Localisation obligatoire** : par la parcelle, la commune ou un point GPS. C'est indispensable pour la veille sanitaire.
- **Historique.** Chaque exploitant retrouve ses diagnostics avec la photo conservée.
- **Alerte de foyer.** Quand une commune atteint le seuil de cas d'une même maladie, les exploitants de la commune et les agents sont prévenus.
- **Météo réelle (Open-Meteo).**
  - Prévisions sur 7 jours par commune, position GPS ou parcelle.
  - Alerte vert, orange ou rouge avec pictogramme.
  - Indication s'il faut semer ou traiter.

## 4. Marché agricole

- **Annonces de récolte.** Produit, quantité, prix et lieu. Une annonce peut être rattachée à une parcelle pour la traçabilité.
- **Catalogue public** filtrable par commune, département, produit et prix maximum.
- **Mise en relation directe.** Un bouton d'appel et un lien WhatsApp avec message pré-rempli.
- **Intérêt des acheteurs.** Un acheteur signale son intérêt, et le producteur est notifié et voit ses coordonnées.
- **Cycle de vie.** Une annonce peut être modifiée, marquée vendue (avec quantité et prix réels) ou retirée.
- **Prix de référence** par produit et département, en distinguant le prix demandé du prix obtenu.

## 5. Supervision de l'État

- **Tableau de bord national.**
  - Surfaces, production prévue et réelle, litiges, transferts en attente, vérifications.
  - Menaces sanitaires, volumes du marché.
  - Terres de l'État, concessions actives.
- **Redevance simulée de 1,5 %.** Elle est calculée sur les ventes déclarées, avec à part le potentiel des annonces actives.
- **Statistiques** par département, par commune et par culture.
- **Veille sanitaire.** Les foyers sont regroupés par commune et par maladie, avec un niveau d'alerte.
- **Cartes GeoJSON** des parcelles et des diagnostics, filtrables selon la zone affichée.

## 6. Domaine privé de l'État et performance

- **Terres de l'État** enregistrées par GPS, avec la référence du titre foncier.
- **Score de performance sur 100.**
  - Il combine cinq critères : productivité comparée aux voisins, fiabilité des prévisions, régularité, conformité et ventes.
  - Chaque critère est expliqué, et seules les parcelles vérifiées comptent.
  - Les agents disposent d'un classement filtrable.
- **Appel à candidatures, conforme à la logique de la concession du Code foncier et domanial.**
  - Rédaction par un agent, publication par un superviseur.
  - Candidatures, classement, proposition justifiée, validation par une autre personne.
  - Délai de contestation, acceptation par le lauréat.
  - Concession active seulement après enregistrement de l'acte officiel.
- **Suivi des concessions.** Récoltes déclarées, inspections de mise en valeur, paiement des redevances, puis retrait ou fin.
- **Garde-fous.**
  - Principe des « quatre yeux » : personne ne valide sa propre décision.
  - Signalement de tout choix hors de l'ordre du classement.
  - Historique horodaté de chaque étape et vue publique transparente.

## 7. Information et réglementation

- **Fiches pratiques** en cinq catégories : produits interdits, normes sanitaires, lois et démarches, bonnes pratiques, FAQ.
- **Accessibilité.** Pictogrammes, résumés simples, lecture audio et recherche par culture ou par mot-clé.
- **Gestion par les agents.** Ils créent, modifient et suppriment les fiches. Les fiches fournies sont des exemples à faire valider par le MAEP.

## 8. Fonctions transverses

- **Notifications** dans l'application pour les litiges, transferts, alertes sanitaires, acheteurs, appels et concessions.
- **Mode hors ligne.** Un envoi rejoué ne crée pas de doublon, et la date réelle de la photo est prise en compte.
- **Audio en MP3 léger** (environ 4 Ko par seconde) pour les diagnostics et les fiches, mis en cache.
- **Adapté aux faibles connexions.** Images réduites, pagination partout, cache météo.
- **Sécurité.** Jetons signés, droits vérifiés sur chaque route, secrets générés aléatoirement, conteneur non-root.
- **Démonstration.** Environ 200 parcelles sur les 12 départements, et 4 comptes de test (exploitant, acheteur, agent, superviseur).
- **Qualité.** 51 tests automatiques et un guide d'intégration pour l'équipe frontend dans le `README.md`.

## 9. Points en attente

| Point | Responsable | Statut |
|---|---|---|
| Brancher un vrai fournisseur SMS | Équipe technique | À faire |
| Valider le contenu réglementaire (fiches) | MAEP / services habilités | À faire |
| Aligner les délais de la procédure d'attribution sur les textes | ANDF / juriste | À faire |
| Vérifier les requêtes géographiques sur MongoDB réel | Équipe technique | À faire |
| Faire relire les textes en fon et yoruba | Locuteurs natifs | À faire |
| Développer le frontend | Équipe frontend | À démarrer |

## 10. Historique des modifications

| Version | Date | Modifications |
|---|---|---|
| 3.1.0 | 24/09/2026 | Domaine privé de l'État : terres, appels à candidatures, contestations, concessions. Score de performance des exploitants. Rôle superviseur. |
| 3.0.0 | 24/09/2026 | Connexion par code SMS simulé et renouvellement de session. Mode hors ligne. Photos des diagnostics. Audio MP3. Notifications. Vérification et transfert de parcelles. Intérêt des acheteurs et prix de référence. Données de démonstration. Tests automatiques. |
| 2.0.0 | 24/09/2026 | Parcelles par contour GPS et détection des chevauchements. Litiges. Récoltes réelles. Diagnostics localisés. Météo réelle. Tableau de bord, statistiques et cartes de l'État. Module réglementaire. |
| 1.1.0 | 24/09/2026 | Corrections de sécurité : jetons JWT, secrets hors du code, appel IA asynchrone, validations. |
| 1.0.0 | 24/09/2026 | Squelette initial : auth NPI, parcelles, diagnostic IA, marché, tableau de bord. |
