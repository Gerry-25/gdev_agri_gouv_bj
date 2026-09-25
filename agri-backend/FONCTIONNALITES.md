# AgriSmart Bénin : fonctionnalités de la plateforme

> Document de référence tenu à jour à chaque ajout ou modification.
> **Backend : 4.0.1 · Frontend : 0.4.0 (intégration du template : étape 3 sur 5)**, dernière mise à jour : 24/09/2026.
> Détails techniques : `README.md` de chaque dossier (`agri-backend`, `agri-frontend`).

## Sommaire

1. [Authentification et profils](#1-authentification-et-profils)
2. [Foncier, parcelles et rendements](#2-foncier-parcelles-et-rendements)
3. [Monitoring et diagnostic phytosanitaire](#3-monitoring-et-diagnostic-phytosanitaire)
4. [Marché agricole](#4-marché-agricole)
5. [Supervision de l'État](#5-supervision-de-létat)
6. [Domaine privé de l'État et performance](#6-domaine-privé-de-létat-et-performance)
7. [Information et réglementation](#7-information-et-réglementation)
8. [Fonctions transverses](#8-fonctions-transverses)
9. [Assistance IA](#9-assistance-ia)
10. [Frontend](#10-frontend)
11. [Points en attente](#11-points-en-attente)
12. [Historique des modifications](#12-historique-des-modifications)

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
- **Qualité.** 65 tests automatiques et un guide d'intégration pour l'équipe frontend dans le `README.md`.

## 9. Assistance IA

**Principe : l'IA propose, l'humain décide.** Chaque sortie est enregistrée comme « proposition », avec le modèle utilisé, la date et les données prises en compte. Les attributions, vérifications, litiges et scores restent des décisions humaines.

**Autres garanties**
- Aucune donnée personnelle n'est envoyée à Gemini : pas de NPI, de nom ni de téléphone. Les parties d'un litige deviennent « partie A » et « partie B ».
- Les réponses identiques sont mises en cache, et un quota quotidien s'applique par utilisateur.
- Sans IA disponible, les calculs par règles continuent de fonctionner : lecture du sol, risque de stockage, priorités d'inspection, prix conseillé.

### Terres de l'État : plan de mise en valeur

- **Profil environnemental automatique** à partir du contour GPS :
  - sol à 30 m (iSDAsoil), avec son niveau d'incertitude ;
  - climat sur 10 ans : saisons des pluies, poches sèches, jours de forte chaleur ;
  - relief : pente, bas-fonds ;
  - distances à la route, au cours d'eau et au marché ;
  - zone agroécologique suggérée.
- **Relevé de terrain de l'agent** : historique d'usage, eau, inondations, couvert, érosion, accès en saison des pluies, infrastructures, main-d'œuvre, usages coutumiers, analyse de sol au laboratoire. Jusqu'à 12 photos géolocalisées.
- **Orientations de l'État** : vocation, cultures prioritaires ou exclues, niveau d'investissement, mécanisation, part minimale à mettre en valeur.
- **Liste de contrôle** de ce qui manque avant de générer le plan.
- **Plan généré par l'IA**, avec le modèle le plus puissant et les photos jointes :
  - aptitude de chaque culture ;
  - deux ou trois scénarios avec rendements, coûts et revenus en fourchettes ;
  - calendrier cultural, plan de fertilité, risques et parades ;
  - indicateurs de mise en valeur contrôlables lors des inspections ;
  - données manquantes et niveau de confiance.
- **Relecture par un expert** (INRAB, ATDA…), enregistrée par un autre agent que l'auteur. Seul un plan validé est montré aux candidats.
- **Appel prérempli** à partir du plan : cahier des charges, cultures, délai de mise en valeur.
- **Aide à l'analyse des candidatures** : points forts, écarts, risques, questions à poser. Un contrôle automatique vérifie que la production annoncée est réaliste au regard du plan.

### Pour l'exploitant

- **Plan de fumure par parcelle**, adapté au sol réel, aux ressources organiques disponibles et au budget, avec lecture audio.
- **Assistant en texte ou à la voix**.
  - Il répond **uniquement à partir des fiches pratiques validées** et cite ses sources.
  - Sans fiche validée sur le sujet, il invite à consulter un conseiller plutôt que d'inventer.
- **Questions de suivi sur un diagnostic**, avec la photo prise en compte.
- **Conseiller de stockage.**
  - Déclaration des stocks, avec un risque de pertes expliqué : méthode, humidité, durée, climat, insectes, moisissures.
  - Rappels de contrôle.
  - Conseil « vendre, vendre en partie ou stocker » tenant compte des prix observés sur la plateforme.
- **Aide à la vente.** Fourchette de prix conseillée et brouillon d'annonce rédigé à partir d'une photo et de quelques mots.

### Pour les agents

- **Synthèse neutre et anonymisée d'un litige** pour la médiation : chronologie, faits établis, points de désaccord, pièces à demander.
- **Priorités d'inspection** calculées par des règles transparentes :
  - parcelles anciennes non vérifiées ;
  - rendements anormaux par rapport aux voisins ;
  - concessions en retard ou impayées ;
  - foyers sanitaires.
- **Note hebdomadaire** nationale ou départementale.
- **Analyse du suivi d'une concession**, avec alerte précoce de défaut.
- **Vue d'ensemble des stocks et pertes déclarés.**

## 10. Frontend

Une seule application (`agri-frontend/apps/web`), basée sur le template AgriSmart Bénin Pro. Les rubriques affichées dépendent du rôle réel de l'utilisateur.

### Avancement de l'intégration du template

| Étape | Contenu | Statut |
|---|---|---|
| 1. Structure et accueil | En-tête, navigation par rôle, connexion, notifications, langue, « Mon exploitation », accueil agent et superviseur | **Livrée** |
| 2. Cadastre | Carte, relevé GPS, fiche parcelle, plan de fumure | **Livrée** |
| 3. Diagnostic et stockage | Scanner photo, questions de suivi, météo, conseiller de stockage | **Livrée** |
| 4. Marché et supervision | Catalogue, annonces avec aide IA, portail acheteur, supervision, litiges, note hebdomadaire | À faire |
| 5. Terres de l'État et conseils | Préparation des terres, plan IA, appels, candidatures, concessions, fiches et assistant vocal | À faire |

### Fonctionnalités livrées

- **Style du template** conservé, avec des corrections :
  - sur téléphone, une barre d'onglets en bas d'écran et plus de débordement horizontal ;
  - aucun texte sous 12 px ;
  - des zones tactiles plus grandes ;
  - une police très lisible, embarquée pour fonctionner hors ligne.
- **Connexion par NPI et code SMS**, au style du template. En mode démonstration, un accès rapide aux 4 comptes passe par la vraie connexion.
- **Navigation par rôle**, sans sélecteur de rôle.
- **Indicateur réel du réseau** et des envois en attente.
- **Menu de la langue des conseils de l'IA**, notifications réelles et menu du compte.
- **« Mon exploitation »**, avec les vraies données :
  - parcelles et leur statut de vérification ;
  - dernières récoltes ;
  - score et ses cinq critères avec leur poids ;
  - annonces et acheteurs intéressés, avec WhatsApp vers leur numéro ;
  - météo de la parcelle ;
  - alertes « terres de l'État ouvertes » et « stock à risque ».
- **Accueil agent et superviseur** : indicateurs nationaux et priorités d'inspection.
- **Cadastre** :
  - **cartes** : fond vectoriel du Bénin hébergé par nous, vue satellite Esri quand une clé est configurée et que le réseau est disponible, carte gardée dans le téléphone pour le terrain ;
  - **relevé GPS en marchant** : écran maintenu allumé, points imprécis refusés, point automatique tous les 10 m, brouillon sauvegardé ; ou **tracé sur la carte** ;
  - **contrôles pendant le relevé** : surface estimée en direct, alerte si les côtés se croisent ou si un point sort du Bénin ;
  - **envoi hors ligne** : sans réseau, la parcelle part dans la file d'attente, sans doublon ;
  - **fiche parcelle** : surface calculée par le serveur, contour, récoltes, lecture du sol, plan de fumure par l'IA avec écoute audio, litiges, météo ;
  - **actions du propriétaire** : refaire le contour, modifier, transférer, supprimer ;
  - **vérification de terrain** par un agent ;
  - **carte nationale des agents** : chargement de la zone visible uniquement, filtres (à vérifier, en litige, vérifiées), points aux petites échelles et contours en zoomant.
- **Diagnostic** :
  - **photo prise depuis le champ**, réduite dans le téléphone avant l'envoi (environ 300 Ko au lieu de plusieurs Mo) ;
  - **localisation** par la parcelle, la commune ou la position GPS ;
  - **résultat** : couleur de gravité, résumé en langage simple **lu à voix haute**, étapes numérotées, conseil détaillé ;
  - **questions de suivi à l'IA**, avec la photo prise en compte ;
  - **historique** avec les photos ;
  - **sans réseau**, la photo est gardée dans le téléphone et le diagnostic est fait automatiquement au retour de la connexion, avec la date réelle de la photo ;
  - **veille sanitaire des agents** : carte des diagnostics colorés par gravité et liste des foyers par commune et maladie.
- **Conseiller de stockage** :
  - déclaration d'un stock (y compris hors ligne) ;
  - risque de pertes expliqué ;
  - contrôle à faire signalé ;
  - saisie d'un contrôle (humidité, insectes, moisissures) ;
  - conseil « vendre maintenant, vendre une partie ou stocker » avec le prix récent ;
  - clôture du stock avec les pertes.
- **Retraits** : le sélecteur de rôle, le téléchargement du code source et les libellés inexacts (« Vérifiée ANDF », classement fictif).

## 11. Points en attente

| Point | Responsable | Statut |
|---|---|---|
| Brancher un vrai fournisseur SMS | Équipe technique | À faire |
| Valider le contenu réglementaire (fiches) | MAEP / services habilités | À faire |
| Aligner les délais de la procédure d'attribution sur les textes | ANDF / juriste | À faire |
| Vérifier les requêtes géographiques sur MongoDB réel | Équipe technique | À faire |
| Faire relire les textes en fon et yoruba | Locuteurs natifs | À faire |
| Intégrer le template (étapes 2 à 5) | Équipe frontend | En cours |
| Traduire les écrans en fon et yoruba | Locuteurs natifs | À faire |
| Tester l'image Docker du frontend (nginx) | Équipe technique | À faire |
| Générer le fond de carte du Bénin (`scripts/build-benin-tiles.sh`) | Équipe technique | À faire |
| Créer la clé Esri gratuite et surveiller le volume de tuiles (moins d'un million par mois) | Équipe technique | À faire |
| Demander à l'ANDF si des orthophotos cadastrales peuvent être fournies | Porteur du projet | À explorer |
| Créer le compte gratuit iSDAsoil et renseigner les identifiants | Équipe technique | À faire |
| Tester l'IA avec une vraie clé Gemini et les services externes réels | Équipe technique | À faire |
| Nouer un partenariat de relecture des plans et des fiches (INRAB, ATDA) | Porteur du projet | À faire |
| Compléter les zones agroécologiques 1 à 5, 7 et 8 (communes, caractéristiques) | MAEP / SNISA | À faire |
| Calibrer les repères du conseiller de stockage (humidité, risques) | INRAB | À faire |
| Décider si la lecture des pièces foncières par l'IA est acceptable (elle implique d'envoyer des noms) | Porteur du projet | À décider |
| Fonctions IA restantes : mise en relation acheteurs, dossier de crédit, estimation des besoins en engrais, planification du matériel, suivi de l'évolution d'une maladie | Équipe technique | À faire |

## 12. Historique des modifications

| Version | Date | Modifications |
|---|---|---|
| Front 0.4.0 / 4.0.2 | 25/09/2026 | Intégration du template, étape 3 : Diagnostic (photo compressée, résultat audio, questions de suivi, historique, envoi différé hors ligne, veille sanitaire des agents) et conseiller de stockage. Backend : l'historique des questions est renvoyé avec le diagnostic. |
| Front 0.3.0 | 25/09/2026 | Intégration du template, étape 2 : Cadastre (cartes MapLibre, fond vectoriel hébergé et hors ligne, vue satellite Esri, relevé GPS ou tracé sur carte, fiche parcelle avec récoltes, sol et plan de fumure, carte nationale des agents). |
| Front 0.2.0 / 4.0.1 | 25/09/2026 | Intégration du template, étape 1 : application unique (structure, connexion, notifications, « Mon exploitation », accueil agent et superviseur), remplace les deux applications précédentes. Backend : rééquilibrage des priorités d'inspection (les anciennes déclarations ne masquent plus les foyers sanitaires). |
| 4.0.0 | 25/09/2026 | Assistance IA : plan de mise en valeur des terres de l'État (profil environnemental automatique, relevé de terrain, orientations, photos, relecture experte, appel prérempli, analyse des candidatures), plan de fumure, assistant texte et voix adossé aux fiches validées, questions de suivi sur un diagnostic, conseiller de stockage, aide à la vente, synthèse de litige, priorités d'inspection, note hebdomadaire, analyse des concessions. Service d'IA centralisé : journal, cache, quotas, anonymisation. |
| Front 0.1.0 | 24/09/2026 | Frontend, étape 1 : socle des deux applications (connexion, session, hors ligne, notifications, profil, vue d'ensemble agents). Backend : export du contrat OpenAPI, service `web` dans Docker Compose. |
| 3.1.0 | 24/09/2026 | Domaine privé de l'État : terres, appels à candidatures, contestations, concessions. Score de performance des exploitants. Rôle superviseur. |
| 3.0.0 | 24/09/2026 | Connexion par code SMS simulé et renouvellement de session. Mode hors ligne. Photos des diagnostics. Audio MP3. Notifications. Vérification et transfert de parcelles. Intérêt des acheteurs et prix de référence. Données de démonstration. Tests automatiques. |
| 2.0.0 | 24/09/2026 | Parcelles par contour GPS et détection des chevauchements. Litiges. Récoltes réelles. Diagnostics localisés. Météo réelle. Tableau de bord, statistiques et cartes de l'État. Module réglementaire. |
| 1.1.0 | 24/09/2026 | Corrections de sécurité : jetons JWT, secrets hors du code, appel IA asynchrone, validations. |
| 1.0.0 | 24/09/2026 | Squelette initial : auth NPI, parcelles, diagnostic IA, marché, tableau de bord. |
