# WayTrace

> **Les archives n'oublient jamais.**

[Read in English](README.md)

Outil de reconnaissance OSINT passive qui reconstruit l'historique numerique complet de n'importe quel domaine a partir de la Wayback Machine (archive.org). Entrez un domaine — WayTrace recupere les pages HTML archivees sur plusieurs decennies, selectionne intelligemment les snapshots les plus pertinents, et extrait 10 categories de donnees de renseignement. Chaque resultat inclut des horodatages `first_seen` / `last_seen`, offrant une chronologie complete de ce qui est apparu, a change et a disparu au fil du temps.

**Aucun scan actif. Aucun brute-force. Uniquement des donnees publiques d'archive.org.**

![MIT License](https://img.shields.io/badge/license-MIT-blue)
![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![Tests](https://img.shields.io/badge/tests-90_passing-brightgreen)

---

## Sommaire

- [Fonctionnement](#fonctionnement)
- [Pipeline de scan](#pipeline-de-scan)
- [Interface](#interface)
- [Categories d'extraction](#categories-dextraction)
- [Resultats cles et severite](#resultats-cles-et-severite)
- [Demarrage rapide](#demarrage-rapide)
- [Reference API](#reference-api)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Tests](#tests)
- [Cadre legal et ethique](#cadre-legal-et-ethique)

---

## Fonctionnement

```
  domaine en entree
       |
       v
+---------------------------------------------------------------------+
|  Phase 1 - Requete CDX                                              |
|  -------------------------------------------------------------------+
|  Interroge l'API CDX d'archive.org -> toutes les URLs HTML archivees|
|  Filtre : text/html uniquement, statut 200, pagine (resumeKey)      |
|  Cache local gzip dans data/cdx/ pour eviter les appels redondants  |
|  Resultat : jusqu'a 50 000+ enregistrements avec timestamps/digests |
+--------------------------------+------------------------------------+
                                 |
                                 v
+---------------------------------------------------------------------+
|  Phase 2 - Selection intelligente des snapshots                     |
|  -------------------------------------------------------------------+
|  Score chaque chemin URL par valeur OSINT (HAUT / MOYEN / BAS)      |
|  Deduplication par digest CDX (supprime le contenu identique)       |
|  Application du preset de profondeur (rapide / standard / complet)  |
|  Plafond adaptatif selon la taille du domaine                       |
+--------------------------------+------------------------------------+
                                 |
                                 v
+---------------------------------------------------------------------+
|  Phase 3 - Scraping                                                 |
|  -------------------------------------------------------------------+
|  Telecharge le HTML depuis la Wayback Machine pour chaque snapshot   |
|  Requetes concurrentes (semaphore), delai adaptatif entre requetes  |
|  Backoff automatique sur rate-limiting 429, retry sur erreurs       |
|  Suppression de la toolbar/scripts injectes par la Wayback Machine  |
+--------------------------------+------------------------------------+
                                 |
                                 v
+---------------------------------------------------------------------+
|  Phase 4 - Extraction et agregation                                 |
|  -------------------------------------------------------------------+
|  Parsing HTML avec selectolax (base C, ~10x plus rapide que BS4)    |
|  Application de 10 categories d'extraction (regex + DOM + JSON-LD)  |
|  Agregation : first_seen, last_seen, occurrences par resultat      |
|  Classement par severite (CRITIQUE > HAUT > MOYEN > BAS)           |
+--------------------------------+------------------------------------+
                                 |
                                 v
                    Resultats OSINT structures
                    avec metadonnees temporelles
```

---

## Pipeline de scan

### Pre-vol (Preflight)

Avant de lancer un scan complet, WayTrace execute un **preflight leger** — uniquement la Phase 1 (requete CDX). Aucune page n'est telechargee. Le preflight retourne :

- Nombre total de snapshots et chemins uniques
- Plage de dates (premier archive au dernier archive)
- Configuration suggeree (plafond adaptatif)
- Navigateur de snapshots par chemin avec scores (mode Avance)

Cela permet d'evaluer la taille des archives d'un domaine et d'ajuster les parametres avant de lancer un scan complet.

### Selection intelligente des snapshots

Toutes les pages archivees n'ont pas la meme valeur. WayTrace attribue a chaque chemin URL un **score OSINT** :

| Score | Chemins | Interet |
|-------|---------|---------|
| **HAUT (3)** | `/contact`, `/about`, `/team`, `/staff`, `/people`, `/careers`, `/jobs`, `/login`, `/admin`, `/press`, `/investors`, `/security`, `/partners`, `/privacy`, `/terms`, `/legal`, `/imprint`, `/impressum`, `/blog` | Ou apparaissent generalement les emails, noms, numeros de telephone et endpoints internes |
| **MOYEN (2)** | Page d'accueil `/` | Suit les changements de branding, stack technique et proprietaire |
| **BAS (1)** | Tout le reste | Contenu general |

**Deduplication du contenu** — CDX fournit un digest SHA-1 pour chaque snapshot. Les snapshots avec le meme `chemin + digest` sont regroupes sur la premiere occurrence, evitant les scrapes redondants de pages identiques. Desactivable via l'option `smart_dedup`.

**Plafond adaptatif** — Le nombre maximum de pages a scraper est calcule selon la taille du domaine :

| Chemins uniques | Plafond par defaut |
|-----------------|-------------------|
| <= 30 | Tous les snapshots HTML |
| <= 200 | min(chemins x 15, 10 000) |
| <= 1000 | min(chemins x 8, 15 000) |
| > 1000 | 15 000 |

**Presets de profondeur** ajustent le plafond :

| Preset | Multiplicateur | Min/Max | Cas d'usage |
|--------|---------------|---------|-------------|
| **Rapide (quick)** | x 0.15 | min 200 | Apercu rapide, changements recents |
| **Standard** | x 1.0 | — | Couverture equilibree (defaut) |
| **Complet (full)** | x 2.0 | max 30 000 | Profondeur d'extraction maximale |

---

## Interface

### Panneau de configuration (apres preflight)

Apres le preflight, le panneau de configuration apparait avec :

- **Nombre de snapshots** — total de snapshots HTML trouves, chemins uniques, plage de dates
- **Plage de dates** — possibilite de restreindre le scan a une periode specifique
- **Preset de profondeur** — rapide / standard / complet
- **Curseur de budget** — plafonner manuellement le nombre de pages
- **Selecteur de categories** — activer/desactiver les 10 categories d'extraction
- **Dedup intelligent** — lorsqu'active (par defaut), ignore les snapshots avec un digest CDX identique
- **Navigateur de snapshots** — arborescence de tous les chemins decouverts avec comptage par chemin ; cocher/decocher des snapshots individuels pour un controle precis (mode Avance)

### Onglets de resultats

Une fois le scan termine, les resultats sont organises en 10 onglets. Chaque onglet partage les memes controles :

- **Barre de recherche globale** — recherche dans TOUS les onglets simultanement
- **Compteur d'onglet** — affiche `filtres/total` quand un filtre est actif ; les onglets avec des correspondances sont mis en surbrillance
- **Tri par colonne** — cliquer sur l'en-tete d'une colonne pour trier croissant/decroissant
- **Copie de colonne** — copie en un clic de toutes les valeurs d'une colonne (ex: toutes les adresses email)
- **Export** — JSON (resultats complets + metadonnees), CSV (onglet courant), All CSV (toutes les categories dans un fichier)

---

## Categories d'extraction

### Emails
Adresses email extraites du HTML brut (incluant les formes obfusquees et les liens mailto). Filtrage du bruit : `noreply`, `no-reply`, `example`, extensions de fichiers image et adresses placeholder sont exclues automatiquement.

**Champs :** `value`, `first_seen`, `last_seen`, `occurrences`

---

### Phones
Numeros de telephone aux formats internationaux et locaux (E.164, US, francais, UK, allemand...). Chaque correspondance est validee : minimum 7 chiffres, maximum 15, pas une date, pas une IP, pas un numero de version. Extrait egalement les liens `tel:` href. Formes brute et normalisee stockees.

**Champs :** `raw`, `normalized`, `first_seen`, `last_seen`, `occurrences`

---

### Subdomains
Sous-domaines du domaine cible trouves dans les liens, scripts, iframes et texte. Utile pour la cartographie de la surface d'attaque : dev, staging, api, mail, cdn et les sous-domaines internes sont souvent references dans les pages archivees meme apres leur mise hors ligne.

**Champs :** `value`, `first_seen`, `last_seen`, `occurrences`

---

### Endpoints
Chemins URL internes decouverts a partir des liens `<a href>` et des attributs `<form action>` sur toutes les pages scrapees. Chaque chemin est suivi avec sa premiere et derniere apparition, donnant une carte temporelle de la structure du site.

**Champs :** `path`, `first_seen`, `last_seen`, `occurrences`

---

### Trackers
Identifiants de trackers analytics et marketing integres au site :

| Tracker | Motif |
|---------|-------|
| Google Analytics (Universal) | `UA-XXXXXXXX-X` |
| Google Analytics 4 | `G-XXXXXXXXXX` |
| Google Tag Manager | `GTM-XXXXXXX` |
| Google Ads | `AW-XXXXXXXXX` |
| Meta Pixel | `fbq(...)` |
| Hotjar | `hjid: XXXXXXX` |
| Mixpanel | `mixpanel.init("...")` |

Les changements d'ID de tracking dans le temps indiquent des transferts de propriete, rebranding ou gestion tierce de l'analytics.

**Champs :** `type`, `id`, `first_seen`, `last_seen`, `occurrences`

---

### Socials
Identifiants de profils de reseaux sociaux extraits des liens. Detecte : Twitter/X, LinkedIn (personnel et entreprise), Facebook, Instagram, Telegram, YouTube, GitHub, TikTok, Snapchat. Exclut les liens de partage/intent.

**Champs :** `platform`, `handle`, `url`, `first_seen`, `last_seen`, `occurrences`

---

### Persons
Noms de personnes identifies a partir de :
- Balises `<meta name="author">` et `<meta property="article:author">`
- Donnees structurees JSON-LD (`@type: Person`, `author`)
- Elements HTML avec classes CSS author/byline/writer

**Champs :** `name`, `context`, `first_seen`, `last_seen`, `occurrences`

---

### Tech Stack
Detection technologique a partir de signaux multiples :
- Balises `<meta name="generator">` et `<meta name="powered-by">`
- Signatures dans les commentaires HTML (`<!-- WordPress 6.2 -->`)
- Indicateurs de classes CSS (`wp-content`, `drupal`, `joomla`)
- URLs de scripts/liens matchees contre des patterns de frameworks connus (React, Angular, Vue.js, Next.js, Nuxt, Svelte, Bootstrap, Tailwind, jQuery, D3.js, Lodash, Moment.js...)
- References CDN (Cloudflare, jsDelivr, unpkg, Google Fonts, Font Awesome)

Les changements de technologie dans le temps (`first_seen != last_seen`) sont signales dans les Resultats Cles.

**Champs :** `technology`, `version`, `first_seen`, `last_seen`, `occurrences`

---

### Cloud Buckets
URLs de stockage cloud exposees dans le code source des pages :

| Fournisseur | Motif |
|-------------|-------|
| Amazon S3 | `*.s3.amazonaws.com/*` |
| Google Cloud Storage | `storage.googleapis.com/*` |
| Azure Blob Storage | `*.blob.core.windows.net/*` |
| DigitalOcean Spaces | `*.digitaloceanspaces.com/*` |

Les URLs de buckets exposees peuvent indiquer un acces public mal configure. Toujours signalees comme **CRITIQUE** dans les Resultats Cles.

**Champs :** `value`, `first_seen`, `last_seen`, `occurrences`

---

### API Keys
Identifiants et tokens API codes en dur trouves dans le code source des pages :

| Type | Motif |
|------|-------|
| AWS Access Key | `AKIA[0-9A-Z]{16}` |
| Google API Key | `AIza[0-9A-Za-z_-]{35}` |
| Stripe Secret/Public | `sk_live_...` / `pk_test_...` |
| Mailgun API Key | `key-[a-zA-Z0-9]{32}` |
| Twilio Auth Token | `SK[a-fA-F0-9]{32}` |
| SendGrid API Key | `SG.[...]{22}.[...]{43}` |
| Slack Webhook | `hooks.slack.com/services/T.../B...` |
| GitHub Token | `ghp_...` / `gho_...` / `ghs_...` / `ghu_...` / `ghr_...` |

Toujours **CRITIQUE** — verifier si les cles exposees sont encore actives via les endpoints de validation des fournisseurs respectifs.

**Champs :** `type`, `value`, `first_seen`, `last_seen`, `occurrences`

---

## Resultats cles et severite

WayTrace genere automatiquement des resultats priorises a partir des extractions. Les resultats sont classes en quatre niveaux de severite :

| Severite | Declencheur | Action |
|----------|-------------|--------|
| **CRITIQUE** | Cles API trouvees, buckets cloud exposes | Tester la validite des cles, verifier les permissions des buckets |
| **HAUT** | Emails internes `@domaine`, sous-domaines, endpoints sensibles (/api, /admin, /login, /auth, /dashboard, /internal, /staging, /debug, /graphql) | Rechercher sur HaveIBeenPwned, resoudre avec dig, tester les endpoints |
| **MOYEN** | Changements de stack technique, trackers analytics (correlation cross-domaine), personnes identifiees | Verifier les anciennes versions pour les CVE, cross-referencer les IDs tracker, rechercher sur LinkedIn |
| **BAS** | Profils de reseaux sociaux | Cross-referencer les handles sur plusieurs plateformes |

Les resultats CRITIQUE et HAUT sont toujours visibles. Les MOYEN et BAS sont replies par defaut.

---

## Demarrage rapide

### Docker (recommande)

```bash
git clone https://github.com/HXLLO/WayTrace.git
cd WayTrace
cp .env.example .env
docker compose up -d
```

Ouvrir **http://localhost:8000** dans le navigateur.

### Docker (developpement — hot reload)

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up
```

### Manuel

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env
uvicorn main:app --reload
```

Ouvrir **http://localhost:8000**.

---

## Reference API

Documentation Swagger interactive : **http://localhost:8000/docs**

### POST /api/scan/preflight

Requete CDX legere — retourne les statistiques du domaine sans scraper de pages.

```bash
curl -X POST http://localhost:8000/api/scan/preflight \
  -H "Content-Type: application/json" \
  -d '{"domain": "example.com"}'
```

```json
{
  "domain": "example.com",
  "total_snapshots": 47404,
  "html_snapshots": 12861,
  "unique_paths": 971,
  "unique_content": 8203,
  "date_range": { "first": "2003-08", "last": "2026-01" },
  "suggested_config": { "cap": 800 },
  "path_groups": [
    { "path": "/", "score": 2, "count": 412, "first": "20030801...", "last": "20260115...", "snapshots": [...] },
    { "path": "/contact", "score": 3, "count": 89, "first": "...", "last": "...", "snapshots": [...] }
  ]
}
```

---

### POST /api/scan

Cree un scan complet. Retourne immediatement un `job_id` ; polling ou streaming pour les resultats.

```bash
curl -X POST http://localhost:8000/api/scan \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "example.com",
    "config": {
      "depth": "standard",
      "cap": 300,
      "date_from": "2018-01",
      "date_to": null,
      "categories": ["emails", "subdomains", "api_keys", "phones"],
      "smart_dedup": true
    }
  }'
```

`config` est optionnel — l'omettre entierement pour utiliser les valeurs par defaut intelligentes.

```json
{ "job_id": "3f8a2c1d-..." }
```

**Mode Avance** — passer `selected_snapshots` (depuis les path_groups du preflight) pour scraper exactement les pages souhaitees :

```json
{
  "domain": "example.com",
  "selected_snapshots": [
    { "timestamp": "20210615120000", "url": "https://example.com/contact" }
  ]
}
```

**Categories valides :** `emails`, `subdomains`, `api_keys`, `cloud_buckets`, `analytics_trackers`, `endpoints`, `social_profiles`, `technologies`, `persons`, `phones`

---

### GET /api/jobs/{job_id}

Polling du statut et recuperation des resultats a la completion.

```json
{
  "id": "3f8a2c1d-...",
  "status": "completed",
  "progress": 100,
  "step": "Scan complete",
  "meta": {
    "domain": "example.com",
    "total_snapshots_found": 12861,
    "snapshots_analyzed": 312,
    "pages_scraped": 298,
    "pages_failed": 14,
    "pages_deduped": 47,
    "date_first_seen": "2003-08",
    "date_last_seen": "2026-01",
    "scan_duration_seconds": 142
  },
  "results": {
    "highlights": [ { "severity": "HIGH", "category": "emails", ... } ],
    "emails": [ { "value": "ceo@example.com", "first_seen": "2009-03", "last_seen": "2021-11", "occurrences": 14 } ],
    "subdomains": [...],
    ...
  }
}
```

Progression du statut : `queued` -> `running` -> `completed` | `failed`

---

### GET /api/jobs/{job_id}/stream

Flux Server-Sent Events pour les mises a jour de progression en temps reel. Prefere au polling.

```bash
curl -N http://localhost:8000/api/jobs/{job_id}/stream
```

```
event: progress
data: {"status": "running", "progress": 42, "step": "Scraping page 126/298"}

event: complete
data: {"status": "completed", "progress": 100, "meta": {...}, "results": {...}}
```

Evenements : `progress`, `complete`, `error`, `expired`. Heartbeat envoye toutes les 15s en idle.

---

### GET /api/health

```json
{ "status": "ok", "uptime_seconds": 3842, "active_jobs": 1 }
```

### GET /api/stats

```json
{ "total_scans_run": 42, "active_jobs": 1 }
```

---

## Configuration

Tous les parametres sont controles via les variables d'environnement dans `.env` (copier depuis `.env.example`) :

| Variable | Defaut | Plage | Description |
|----------|--------|-------|-------------|
| `MAX_CONCURRENT_SCRAPES` | `30` | 1–50 | Requetes paralleles vers la Wayback Machine |
| `ARCHIVE_REQUEST_TIMEOUT` | `30` | 5–120 | Timeout par requete en secondes |
| `ARCHIVE_RETRY_COUNT` | `3` | — | Retentatives sur erreurs CDX/Wayback transitoires |
| `SCRAPE_DELAY_MIN` | `0.02` | — | Delai minimum entre requetes (secondes) |
| `SCRAPE_DELAY_MAX` | `0.08` | — | Delai maximum entre requetes (secondes) |
| `SCRAPE_MAX_RETRIES` | `3` | — | Retentatives par page sur erreurs transitoires |
| `JOB_TTL_SECONDS` | `7200` | — | Expiration des jobs — supprime apres 2 heures |
| `MAX_ACTIVE_JOBS` | `10` | >= 1 | Nombre maximum de scans concurrents |
| `SCAN_TIMEOUT_SECONDS` | `3600` | — | Timeout dur par scan (60 minutes) |
| `PAGE_CACHE_MAX_MB` | `512` | — | Taille maximale du cache de pages en memoire |
| `CDX_CACHE_TTL` | `300` | — | Duree de vie du cache CDX (secondes) |
| `PAGE_CACHE_TTL` | `300` | — | Duree de vie du cache de pages (secondes) |
| `PRESCRAPE_LIMIT` | `15` | — | Max de pages a pre-scraper pendant le preflight |
| `COLLAPSE_THRESHOLD` | `250000` | — | Seuil de resultats CDX pour le regroupement mensuel |
| `SCAN_RATE_LIMIT_RPM` | `10` | 0 = desactive | Requetes de scan/min par IP |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | — | Origines autorisees (separees par des virgules) |
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR | Verbosity des logs |

---

## Architecture

```
backend/
├── main.py                   App FastAPI, CORS, lifespan (boucle de nettoyage TTL)
├── config.py                 Pydantic settings charge depuis .env
├── models.py                 Tous les schemas requete/reponse (Pydantic v2)
├── store.py                  Store de jobs en memoire, expiration TTL, lock de concurrence
├── routers/
│   ├── scan.py               POST /scan, POST /scan/preflight, GET /jobs/{id}, flux SSE
│   └── health.py             GET /health, GET /stats
└── services/
    ├── cdx.py                Client API CDX — HTML uniquement, pagine (resumeKey), cache gzip
    ├── filters.py            Selection intelligente — scoring des chemins, dedup, presets
    ├── scraper.py            Telechargeur Wayback concurrent — semaphore, backoff adaptatif
    └── extractor/
        ├── patterns.py       Tous les patterns regex (email, phone, API keys, trackers, socials...)
        ├── extract.py        Extraction par page — 10 categories, regex + selectolax DOM
        ├── finalize.py       Orchestration extract_all(), accumulateur -> listes triees
        ├── highlights.py     Classement par severite (CRITIQUE/HAUT/MOYEN/BAS)
        └── helpers.py        Utilitaires — normalize_phone, strip_wayback_artifacts...

frontend/
└── index.html                Fichier HTML unique — JS vanilla, theme sombre, sans build
                              Onglets, colonnes triables, recherche globale, export CSV/JSON

tests/
├── test_api.py               Validation API, cycle de vie des jobs, filtrage par categorie
├── test_extractor.py         Patterns regex, logique d'extraction, highlights
└── test_filters.py           Selection de snapshots, presets de profondeur, filtrage par date, dedup
```

**Stack :** Python 3.12+, FastAPI, aiohttp, selectolax, Pydantic v2, loguru, httpx (tests)

**Decisions de conception :**

- **Pas de base de donnees** — tout l'etat des jobs en memoire ; expiration automatique via boucle TTL en arriere-plan
- **Asynchrone de bout en bout** — aiohttp pour tout l'I/O reseau, aucun appel bloquant en contexte async
- **selectolax** plutot que BeautifulSoup — parser HTML en C, ~10x plus rapide pour le parsing en volume
- **Filtrage CDX cote serveur** — ne demande que `text/html` + `status:200` ; evite de recuperer des milliers d'entrees image/CSS/JS
- **Cache CDX sur disque** — resultats caches en JSON compresse gzip dans `data/cdx/` ; les requetes repetees utilisent le disque au lieu du reseau
- **Deduplication du contenu** — les digests SHA-1 CDX regroupent les snapshots identiques avant le scraping
- **Rate limiting adaptatif** — asyncio.Semaphore + delai aleatoire par requete ; augmente automatiquement le delai sur les 429, recupere progressivement en cas de succes
- **Deduplication de domaine** — soumettre le meme domaine deux fois retourne le meme job ID

---

## Tests

```bash
cd backend
python -m pytest tests/ -v          # les 90 tests
python -m pytest tests/test_extractor.py -v   # patterns d'extraction uniquement
python -m pytest tests/test_filters.py -v     # selection de snapshots uniquement
python -m pytest tests/test_api.py -v         # endpoints API uniquement
```

La couverture inclut :
- Validation des endpoints API (format de domaine, noms de categories, limites de config)
- Cycle de vie des jobs (queued -> running -> completed -> expired)
- Algorithme de selection de snapshots (scoring, presets de profondeur, filtrage par date, deduplication)
- Les 10 categories d'extraction (cas de tests positifs + faux positifs)
- Logique de classement par severite (generation des highlights)

---

## Cadre legal et ethique

WayTrace interroge **uniquement les archives publiques** de la Wayback Machine (archive.org). Il n'effectue aucun scan actif, scan de ports, brute-force, enumeration DNS ou toute action intrusive contre les systemes cibles.

- Destine a la recherche en securite legitime, aux investigations OSINT, au due diligence et a la veille concurrentielle
- Ne pas utiliser pour le harcelement, le stalking ou toute activite illegale
- Les utilisateurs sont seuls responsables de l'utilisation qu'ils font des donnees extraites
- Respecter les conditions d'utilisation d'archive.org — ne pas surcharger les requetes ou tenter de contourner les limites de taux

---

## Licence

[MIT](LICENSE)
