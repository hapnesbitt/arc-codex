# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack Overview

Arc Codex is a news intelligence platform that ingests RSS feeds, analyzes articles via the A.R.C. framework (three independent AI perspectives), and serves them through a Next.js frontend. It runs alongside **Huntaegis** (`/home/www/huntaegis_stack`) as a sibling stack on the same server — same Redis instance (different DB), same Ollama/Solr, same code structure.

## Commands

### Backend
```bash
# Dev (hot reload)
cd backend && source venv/bin/activate && python3 main.py

# Production via Gunicorn (1 worker, 8 threads, port 5005)
cd backend && ./gunicorn_arc.sh

# Run a single service (e.g. scribe) outside Docker
cd backend && source venv/bin/activate && python3 scribe.py
```

### Frontend
```bash
# Dev (Turbopack, port 3000)
cd frontend && npm run dev

# Production build
cd frontend && npm run build

# Type check
cd frontend && npx tsc --noEmit

# Lint
cd frontend && npm run lint
```

### Stack management (production)
```bash
./arc.sh start [service]   # Start all services or one specific service
./arc.sh stop              # Stop all
./arc.sh restart [service] # Restart all or one
./arc.sh status            # PID + port check for all services
./arc.sh logs              # Tail all logs
./arc.sh checkup           # Health check all services
./arc.sh backup            # SSD fast backup (keeps last 5)
./arc.sh backup-cold       # Full cold archive (keeps last 30, includes Redis RDB + Solr)
```

### Docker Compose (alternative to arc.sh)
```bash
docker compose build
docker compose up -d [service]
docker compose logs -f [service]
docker compose restart [service]
```

## Architecture

### Request Flow
1. **Caddy** (TLS termination) → `/api/*` → **Flask** (port 5005) or **Next.js** (port 3000)
2. **Next.js API routes** (`frontend/app/api/`) proxy to Flask via `BACKEND_INTERNAL_URL=http://localhost:5005`
3. **Frontend pages** use `NEXT_PUBLIC_BACKEND_URL` for client-side calls (resolves to `https://arc-codex.com` in prod)

### A.R.C. Analysis Pipeline
Each article receives three independent AI passes (lazy — triggered on first view via `analyzer.py`):
- **Red Team** — Verifiable facts only, bullet points, zero interpretation
- **Blue Team** — Balanced executive summary, journalistic neutrality
- **Purple Team** — Deep analysis: 48 A.R.C. anti-patterns (ARC-0001 to ARC-0048), counterstrike scan, bridge questions

Plus:
- **Sentinel** — AI-content detection (HUMAN < 20%, UNCERTAIN 20-60%, SYNTHETIC > 80%)
- **Counter-Analyst** — Auto-seeded devil's advocate comment (cyan styling, robot emoji)

Prompts live in `backend/prompts.yaml`. The 48 ARC pattern names are canonical — do not rename them without updating prompts.yaml.

### Backend Services (all in `backend/`)
| File | Purpose | Port/Queue |
|------|---------|------------|
| `main.py` | Flask API | 5005 |
| `scribe.py` | RSS ingestion + NLP + analysis dispatch | 13-min cycle |
| `analyzer.py` | On-demand Red/Blue/Purple via Ollama | `analyzer:queue` LIST |
| `manual_publisher.py` | Manual content publishing | `/backend/upload/pending/` |
| `corpus_exporter.py` | Prometheus metrics (NLP fields) | 9101 |
| `mailer.py` | Email alerts + 7am digest | cron |
| `bluesky_poster.py` | Bluesky auto-posting | cron |
| `auth.py` | Flask blueprint — shared with huntaegis | imported |

### Redis Schema (DB 0 for Arc)
```
article:{id}              HASH — all article data + analysis
feed                      ZSET — sorted by timestamp (score)
processed_hashes          SET  — SHA256 dedup
arc:priority_uploads      LIST — priority user submissions (skip analysis queue)
analyzer:queue            LIST — on-demand analysis jobs
translation:langs:{id}    SET  — available translation languages
arc:stats:*               HASH counters
translator:active         STRING — TTL lock prevents model thrashing (300s)
```
DB 5 is shared auth across all stacks (`arc:users` SET, `arc:user:{username}` HASH).

### AI Inference
- **Primary**: Ollama on MacBook Air M1 at `192.168.1.185:11434`
- **Cloud model**: `devstral-2:123b-cloud` (weekly credit limit)
- **Local fallbacks**: `mistral:7b` → `llama3.2:latest`
- **Translation model**: `MedAIBase/TranslateGemma:4b` — uses `/api/chat` endpoint (not `/api/generate`)

### Frontend Key Components
- `components/IntelligenceCard.tsx` — Full article renderer (tabs, scores, menus). Most complex component.
- `components/FeedClient.tsx` — Tribonacci lazy-loading feed with staggered animations
- `components/CopyAllButton.tsx` — Copies full article + analysis to clipboard
- `components/ResearchMenu.tsx` — Opens article in Claude/ChatGPT/Perplexity/Google with context
- `lib/types.ts` — All TypeScript interfaces (Article, Comment, Dossier, etc.)
- `lib/auth.ts` — NextAuth.js config with backend upsert on sign-in

### Environment Variables
**Frontend** (`frontend/.env.local`):
- `NEXT_PUBLIC_BACKEND_URL` — Public URL for client-side fetches (e.g. `https://arc-codex.com`)
- `BACKEND_INTERNAL_URL` — Server-side proxy target (`http://localhost:5005`)
- `NEXTAUTH_URL`, `AUTH_SECRET`, OAuth provider credentials

**Backend** (`backend/.env`):
- `REDIS_URL`, `REDIS_HOST`, `REDIS_PASSWORD`
- `SCRIBE_SOLR_URL`
- `OLLAMA_URL`, `OLLAMA_CLOUD_MODEL`, `OLLAMA_LOCAL_FALLBACK`, `TRANSLATION_MODEL`
- `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`
- `MASTODON_INSTANCE`, `MASTODON_ACCESS_TOKEN`

## Arc ↔ Huntaegis Relationship

The two stacks are nearly identical in code but run independently. When fixing a bug or adding a feature, check whether the same change is needed in `/home/www/huntaegis_stack/`. Key differences:
- Arc: Redis DB 0, port 5005 (API), port 3000 (frontend), `arc:priority_uploads`
- Huntaegis: Redis DB 1, port 5006 (API), port 3001 (frontend), `huntaegis:priority_uploads`
- Domain-specific strings (arc-codex.com vs huntaegis.com, branding) are intentionally different

Shared utilities: `auth.py`, `ollama_utils.py`, `fetch_utils.py`, `stream_utils.py` — changes here may need mirroring.

## Important Constraints

- **`corpus_exporter.py` consumes NLP fields** from Redis as Prometheus gauges. Before removing any field from `pre_analyze`'s Redis write-back, verify it's not consumed there.
- **Semaphore on `pre_analyze`**: `_pre_analyze_sem = threading.Semaphore(2)` limits to 2 concurrent requests, returns 429 after 1s timeout. Do not remove this.
- **Translation lock**: `translator:active` key prevents two translation jobs running simultaneously. The TTL (300s) is intentional.
- **`feed` ZSET ordering**: score = Unix timestamp. Never use `r.keys('article:*')` for feed retrieval — always use `ZRANGE` on the feed ZSET.
- **Ghost hash problem**: Bluesky/Mastodon posters track posted article IDs separately from `processed_hashes`. The two sets can diverge if an article publish fails mid-way.
- **`NEXT_PUBLIC_*` variables** are baked in at build time — changing them requires a Docker rebuild.
