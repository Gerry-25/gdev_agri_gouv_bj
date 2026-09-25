# AgriSmart Bénin : frontend

Une seule application, basée sur le template AgriSmart Bénin Pro. Les rubriques affichées dépendent du rôle
réel de l'utilisateur (exploitant, acheteur, agent, superviseur).

| Dossier | Contenu |
|---|---|
| `apps/web` | L'application : installable (PWA), mobile d'abord, Tailwind, style du template |
| `packages/core` | Client API typé, session, file hors ligne, formatage (partagé, testé) |

## Démarrer en développement

Le backend doit tourner sur `http://localhost:8000` (voir `agri-backend`). L'application relaie `/api` vers lui.

```bash
npm install
npm run dev          # http://localhost:5173
```

En mode démonstration (SMS simulé), l'écran de connexion propose un accès rapide aux 4 comptes de démo.
Il passe par la vraie connexion par code, simplement préremplie.

## Cartes

| Élément | Source | Mise en place |
|---|---|---|
| Fond de plan (routes, villages) | OpenStreetMap via Protomaps, **hébergé par nous** (`/tiles/benin.pmtiles`) | `./scripts/build-benin-tiles.sh` (outil `pmtiles` requis) |
| Polices et icônes de la carte | Protomaps (Noto Sans) | déjà dans `apps/web/public/map-assets` ; `./scripts/fetch-map-assets.sh` pour les mettre à jour |
| Vue satellite | Esri World Imagery | clé gratuite ArcGIS Location Platform dans `VITE_ESRI_TOKEN` |

- Sans fichier de tuiles, la carte affiche seulement les parcelles sur un fond neutre (avec un message).
- **Hors ligne** : le fond de plan peut être gardé dans le téléphone (bouton « Carte hors ligne » du Cadastre),
  ce qui est permis car le fichier est le nôtre. La vue satellite n'est pas exportable : elle n'est proposée
  qu'avec du réseau et n'utilise que le cache normal du navigateur.
- Conditions Esri à respecter : application sans revenus (ni publicité ni abonnement), moins d'un million de
  tuiles par mois, mentions « Powered by Esri » et fournisseurs affichées (déjà fait par l'application).
- Le code de carte (MapLibre) est chargé seulement à l'ouverture d'un écran de carte (`scripts/chunks.ts`).

### Relevé GPS

Le relevé en marchant garde l'écran allumé (le GPS d'une application web s'arrête écran éteint), refuse les
points trop imprécis (plus de 30 m), peut ajouter un point automatiquement tous les 10 m, et sauvegarde le
brouillon à chaque point. Sans réseau, la parcelle part dans la file d'attente et sera envoyée plus tard.
La surface affichée pendant le relevé est une estimation ; celle du serveur fait foi.

### Photos et hors ligne

Les photos de diagnostic sont réduites dans le téléphone (1600 px, JPEG) avant l'envoi. Sans réseau, la photo
et le formulaire partent dans la file d'attente (`registerSenders` dans `apps/web/src/lib/senders.ts` : parcelles,
diagnostics, stocks) et sont envoyés au retour de la connexion, avec la date réelle de la photo.

### Assistant vocal

L'enregistrement utilise l'API MediaRecorder du navigateur (WebM/Opus sur Android, MP4 sur iPhone) et
exige HTTPS en production. nginx autorise le micro pour le site (`Permissions-Policy`). La question est
transcrite par Gemini, puis l'assistant ne répond qu'à partir des fiches **validées**.

## Commandes

| Commande | Rôle |
|---|---|
| `npm run typecheck` | Vérifie les types des quatre paquets |
| `npm test` | Tests (session, file hors ligne, erreurs, géométrie du relevé) |
| `npm run build` | Construit l'application |
| `npm run api:pull` | Récupère le contrat OpenAPI du backend en marche et régénère le client |
| `npm run api:generate` | Régénère le client à partir de `openapi.json` |

**Après chaque modification du backend**, régénérez le client (`npm run api:pull`, ou
`python -m app.scripts.export_openapi > ../agri-frontend/openapi.json` puis `npm run api:generate`)
et lancez `npm run typecheck` : TypeScript signale tout écran devenu incompatible.

## Déploiement

Le `Dockerfile` construit l'application et la sert avec nginx, qui relaie `/api` vers le backend.
Placez `agri-frontend` à côté de `agri-backend` : le `docker-compose.yml` du backend contient le service
`web`, accessible sur http://localhost:8080. L'ancienne adresse `/agents/` redirige vers l'application.

## Conventions

### Appeler l'API

Utilisez `api` de `@agri/core` : les routes, paramètres et réponses sont typés depuis le contrat
OpenAPI. Le jeton est ajouté et renouvelé automatiquement ; une session expirée déconnecte l'utilisateur.

```ts
const { data, error } = await api.GET("/api/v1/lands/me");
if (error) throw new Error(apiErrorMessage(error)); // message en français, prêt à afficher
```

### Enregistrer une saisie hors ligne

Toute création faite sur le terrain passe par la file d'attente : elle est gardée dans le téléphone
et envoyée au retour du réseau, sans doublon grâce au `client_ref`.

```ts
// 1. une fois, au démarrage de l'application : comment envoyer ce type de saisie
registerSender("land", async (item) => {
  ensureSent(await api.POST("/api/v1/lands/", { body: item.payload as LandCreate }));
});
// 2. à chaque saisie
await enqueue("land", "Parcelle de manioc", { ...payload, client_ref: newClientRef() });
```

Une erreur de validation (4xx) met la saisie de côté avec son message ; une coupure réseau la garde
en attente et préserve l'ordre. L'écran « Envois en attente » permet de réessayer ou de supprimer.

### Textes et langues

Tous les textes sont dans `packages/core/src/i18n/fr.ts`. Les écrans n'existent qu'en français :
les traductions en fon et yoruba doivent être rédigées et relues par des locuteurs natifs, jamais
générées automatiquement. La langue choisie par l'utilisateur est déjà utilisée par l'IA et l'audio.

### Design

- Style du template : fond `neutral-50`, cartes blanches bordées (`Card`, `CardHeader`), accent émeraude,
  composants de base dans `apps/web/src/components/ui.tsx`.
- Ajustements pour le terrain : police Atkinson Hyperlegible embarquée, **aucun texte sous 12 px**
  (`text-xs`), zones tactiles d'au moins 44 px (`min-h-11`), barre d'onglets en bas d'écran sur téléphone.
- Les couleurs rouge, orange et vert des alertes (météo, gravité, litiges) gardent leur sens : pas d'usage décoratif.
- Libellés exacts : « Vérifiée par un agent » (pas « Vérifiée ANDF »), pas de classement fictif,
  score et critères toujours lus depuis l'API.
- Rubriques par rôle : `apps/web/src/lib/nav.ts`.
