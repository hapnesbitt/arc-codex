#!/bin/bash
# =============================================================================
# provision.sh — Arc Stack Rapid Deployment
# =============================================================================
# Spins up a new intelligence node from the arc-codex template in minutes.
# 
# Usage:
#   ./provision.sh \
#     --name    "NEET Watch" \
#     --slug    "neetwatch" \
#     --domain  "neetwatch.com" \
#     --db      2 \
#     --backend-port 5007 \
#     --frontend-port 3003 \
#     --focus   "social" \
#     --keywords "NEET, youth unemployment, social isolation, disengagement"
#
# --focus presets: general | security | social | finance | health | arts
# --keywords overrides preset directives with custom keyword generation
#
# Prerequisites:
#   - Arc Codex running at /home/www/arc_stack (used as template source)
#   - Redis running with password in arc_stack backend/.env
#   - Solr running at localhost:8983
#   - Ollama running (used for directive generation if --keywords provided)
#   - Python 3, git, docker installed
#
# What it does:
#   1. Validates args and checks prerequisites
#   2. Copies arc_stack → /home/www/{slug}_stack
#   3. Stamps all tokens (domain, ports, redis db, solr core, etc.)
#   4. Creates Redis DB (just sets a test key — Redis DBs are implicit)
#   5. Creates Solr core feeds_{slug}
#   6. Generates directives.json from --focus preset or --keywords via Ollama
#   7. Writes arc_config.yaml with new values
#   8. Creates {slug}.sh, {slug}_env.sh, watchdog.sh from templates
#   9. Creates systemd unit
#  10. Runs git init and first commit
#  11. Prints next steps
# =============================================================================

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
TEMPLATE_ROOT="/home/www/arc_stack"
STACKS_ROOT="/home/www"
STACK_USER="${USER:-ross}"

NAME=""
SLUG=""
DOMAIN=""
REDIS_DB=""
BACKEND_PORT=""
FRONTEND_PORT=""
FOCUS="general"
KEYWORDS=""

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
AMBER='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()   { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${AMBER}⚠${NC}  $1"; }
error() { echo -e "${RED}✗${NC} $1"; exit 1; }
info()  { echo -e "${CYAN}→${NC} $1"; }
step()  { echo -e "\n${BOLD}$1${NC}"; }

# ── Arg parsing ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)           NAME="$2";         shift 2 ;;
    --slug)           SLUG="$2";         shift 2 ;;
    --domain)         DOMAIN="$2";       shift 2 ;;
    --db)             REDIS_DB="$2";     shift 2 ;;
    --backend-port)   BACKEND_PORT="$2"; shift 2 ;;
    --frontend-port)  FRONTEND_PORT="$2";shift 2 ;;
    --focus)          FOCUS="$2";        shift 2 ;;
    --keywords)       KEYWORDS="$2";     shift 2 ;;
    --help|-h)
      sed -n '3,20p' "$0" | sed 's/^# //'
      exit 0
      ;;
    *) error "Unknown argument: $1" ;;
  esac
done

# ── Validate required args ────────────────────────────────────────────────────
[[ -z "$NAME" ]]         && error "--name is required (e.g. 'NEET Watch')"
[[ -z "$SLUG" ]]         && error "--slug is required (e.g. 'neetwatch')"
[[ -z "$DOMAIN" ]]       && error "--domain is required (e.g. 'neetwatch.com')"
[[ -z "$REDIS_DB" ]]     && error "--db is required (e.g. 2, 3, 4...)"
[[ -z "$BACKEND_PORT" ]] && error "--backend-port is required (e.g. 5007)"
[[ -z "$FRONTEND_PORT" ]]&& error "--frontend-port is required (e.g. 3003)"

# Slug must be lowercase alphanumeric + underscore only
[[ "$SLUG" =~ ^[a-z0-9_]+$ ]] || error "--slug must be lowercase alphanumeric/underscore only"

STACK_ROOT="${STACKS_ROOT}/${SLUG}_stack"
SOLR_CORE="feeds_${SLUG}"

# ── Pre-flight checks ─────────────────────────────────────────────────────────
step "🔍 Pre-flight checks"

[[ -d "$TEMPLATE_ROOT" ]] || error "Template not found at $TEMPLATE_ROOT"
[[ -d "$STACK_ROOT" ]]    && error "Stack already exists at $STACK_ROOT — remove it first"

# Get Redis password from template
REDIS_PASSWORD=$(grep "REDIS_PASSWORD=" "$TEMPLATE_ROOT/backend/.env" 2>/dev/null \
  | head -1 | cut -d'=' -f2 | tr -d '"')
[[ -z "$REDIS_PASSWORD" ]] && error "Could not read REDIS_PASSWORD from $TEMPLATE_ROOT/backend/.env"

# Check Redis
redis-cli -a "$REDIS_PASSWORD" ping &>/dev/null || error "Redis not responding"
log "Redis OK"

# Check Solr
curl -sf "http://localhost:8983/solr/admin/cores?action=STATUS" &>/dev/null \
  || error "Solr not responding at localhost:8983"
log "Solr OK"

# Check port availability
for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  lsof -ti:"$port" &>/dev/null && error "Port $port is already in use"
done
log "Ports $BACKEND_PORT and $FRONTEND_PORT available"

# Check Redis DB not in use
KEY_COUNT=$(redis-cli -a "$REDIS_PASSWORD" -n "$REDIS_DB" dbsize 2>/dev/null || echo "0")
[[ "$KEY_COUNT" -gt 0 ]] && \
  warn "Redis DB $REDIS_DB has $KEY_COUNT existing keys — continuing anyway"

log "Pre-flight passed"

# ── Copy template ─────────────────────────────────────────────────────────────
step "📋 Copying template → $STACK_ROOT"

rsync -a \
  --exclude='.git' \
  --exclude='backend/venv' \
  --exclude='frontend/node_modules' \
  --exclude='frontend/.next' \
  --exclude='logs/*' \
  --exclude='pids/*' \
  --exclude='backups/*' \
  --exclude='backend/uploads/*' \
  --exclude='backend/upload/*' \
  --exclude='secret/*' \
  --exclude='*.log' \
  --exclude='*.log.gz' \
  --exclude='*.tar.gz' \
  --exclude='*.swp' \
  --exclude='*.Mar*' \
  --exclude='*.faster' \
  --exclude='Arc_dash.json' \
  --exclude='monitoring/' \
  --exclude='frontend/app/about/developer/config/arc_config.yaml' \
  "$TEMPLATE_ROOT/" "$STACK_ROOT/"

log "Template copied"

# ── Token replacement helper ──────────────────────────────────────────────────
replace_in_file() {
  local file="$1" old="$2" new="$3"
  sed -i "s|${old}|${new}|g" "$file" 2>/dev/null || true
}

replace_in_dir() {
  local dir="$1" old="$2" new="$3"
  grep -rl "$old" "$dir" \
    --exclude-dir='.git' \
    --exclude-dir='venv' \
    --exclude-dir='node_modules' \
    --exclude-dir='.next' \
    --exclude='*.pyc' \
    2>/dev/null | while read -r f; do
    replace_in_file "$f" "$old" "$new"
  done
}

# ── Token substitution ────────────────────────────────────────────────────────
step "🔧 Stamping tokens"

# Stack name (display)
replace_in_dir "$STACK_ROOT" "Arc Codex" "$NAME"

# Domain
replace_in_dir "$STACK_ROOT" "arc-codex.com" "$DOMAIN"
replace_in_dir "$STACK_ROOT" "arc_codex" "${SLUG}"

# Ports
replace_in_dir "$STACK_ROOT" "5005" "$BACKEND_PORT"
replace_in_dir "$STACK_ROOT" "3000" "$FRONTEND_PORT"

# Redis DB
replace_in_dir "$STACK_ROOT" "redis://:${REDIS_PASSWORD}@localhost:6379/0" \
  "redis://:${REDIS_PASSWORD}@localhost:6379/${REDIS_DB}"

# Solr core
replace_in_dir "$STACK_ROOT" "solr/feeds/" "solr/${SOLR_CORE}/"
replace_in_dir "$STACK_ROOT" '"feeds"' "\"${SOLR_CORE}\""

# Stack root paths
replace_in_dir "$STACK_ROOT" "/home/www/arc_stack" "$STACK_ROOT"

# Docker image/container names
replace_in_dir "$STACK_ROOT" "arc-codex-backend" "${SLUG}-backend"
replace_in_dir "$STACK_ROOT" "arc-codex-frontend" "${SLUG}-frontend"
replace_in_dir "$STACK_ROOT" "arc-frontend" "${SLUG}-frontend"
replace_in_dir "$STACK_ROOT" "arc-gunicorn" "${SLUG}-gunicorn"
replace_in_dir "$STACK_ROOT" "arc-scribe" "${SLUG}-scribe"
replace_in_dir "$STACK_ROOT" "arc-mailer" "${SLUG}-mailer"
replace_in_dir "$STACK_ROOT" "arc-analyzer" "${SLUG}-analyzer"
replace_in_dir "$STACK_ROOT" "name: arc-codex" "name: ${SLUG}"

# Stack manager script name
replace_in_dir "$STACK_ROOT" "arc\.sh" "${SLUG}.sh"
replace_in_dir "$STACK_ROOT" "arc_env\.sh" "${SLUG}_env.sh"

# Rename arc.sh → {slug}.sh
[[ -f "$STACK_ROOT/arc.sh" ]] && mv "$STACK_ROOT/arc.sh" "$STACK_ROOT/${SLUG}.sh"
[[ -f "$STACK_ROOT/arc_env.sh" ]] && mv "$STACK_ROOT/arc_env.sh" "$STACK_ROOT/${SLUG}_env.sh"
chmod +x "$STACK_ROOT/${SLUG}.sh"

log "Tokens stamped"

# ── Update arc_config.yaml ────────────────────────────────────────────────────
step "⚙️  Writing arc_config.yaml"

cat > "$STACK_ROOT/arc_config.yaml" << EOF
# arc_config.yaml — ${NAME} Operational Configuration
# Generated by provision.sh on $(date +%Y-%m-%d)

stack:
  name: "${NAME}"
  domain: "${DOMAIN}"
  handle: ""
  root: "${STACK_ROOT}"
  backend_port: ${BACKEND_PORT}
  frontend_port: ${FRONTEND_PORT}
  redis_db: ${REDIS_DB}
  solr_core: "${SOLR_CORE}"

ollama:
  host: "http://192.168.1.185:11434"
  primary_model: "devstral"
  fallback_model: "gemma3:4b"
  translation_model: "MedAIBase/TranslateGemma:4b"
  translation_fields: "pro"

scribe:
  cycle_sleep_seconds: 300
  cycle_sleep_interval: 10
  max_concurrent_analyzers: 4
  priority_queue_key: "scribe:priority_uploads"

bluesky:
  autopost: false
  jitter_min_seconds: 30
  jitter_max_seconds: 180
  counter_analyst_wait_seconds: 60
  poll_interval_seconds: 15

mailer:
  alert_to: "rossnesbitt@gmail.com"
  digest_hour: 7
  stall_threshold_hours: 2
  log_scan_interval_seconds: 60
  log_lookback_minutes: 2

translation:
  cache_ttl_hours: 24
  lock_key: "translation:active"
  lock_ttl_seconds: 300
  ollama_backoff_seconds: 60

feed:
  default_page_size: 33
  max_page_size: 100

backups:
  ssd_keep: 5
  cold_keep: 30
  ssd_cron: "0 4 * * *"
  cold_cron: "0 3 * * 0"

services:
  gunicorn: true
  scribe: true
  analyzer: true
  stream_consumer: true
  manual_publisher: true
  mailer: true
  bluesky_poster: false
  character_builder: true
  corpus_exporter: true
  frontend: true
  watchdog: true
EOF

log "arc_config.yaml written"

# ── Update {slug}_env.sh ──────────────────────────────────────────────────────
cat > "$STACK_ROOT/${SLUG}_env.sh" << EOF
# ${SLUG}_env.sh - Source this before using ${SLUG}.sh
# Usage: source ${STACK_ROOT}/${SLUG}_env.sh
# Add to ~/.bashrc: source ${STACK_ROOT}/${SLUG}_env.sh

export $( echo "${SLUG^^}" )_ROOT="${STACK_ROOT}"
alias ${SLUG}='${STACK_ROOT}/${SLUG}.sh'
alias ${SLUG}-logs='tail -f ${STACK_ROOT}/logs/*.log'
alias ${SLUG}-status='${STACK_ROOT}/${SLUG}.sh status'

echo "✅ ${NAME} environment loaded. Command: ${SLUG} start|stop|restart|status|logs|build|checkup|backup"
EOF

log "${SLUG}_env.sh written"

# ── Create Solr core ──────────────────────────────────────────────────────────
step "🔍 Creating Solr core: $SOLR_CORE"

SOLR_RESP=$(curl -sf \
  "http://localhost:8983/solr/admin/cores?action=CREATE&name=${SOLR_CORE}&configSet=_default" \
  2>&1 || true)

if echo "$SOLR_RESP" | grep -q '"status":0'; then
  log "Solr core $SOLR_CORE created"
elif echo "$SOLR_RESP" | grep -q "already exists"; then
  warn "Solr core $SOLR_CORE already exists — skipping"
else
  warn "Solr core creation returned unexpected response — check manually"
  echo "$SOLR_RESP" | head -3
fi

# ── Generate directives.json ──────────────────────────────────────────────────
step "📋 Generating directives.json (focus: $FOCUS)"

DIRECTIVES_FILE="$STACK_ROOT/backend/directives.json"

if [[ -n "$KEYWORDS" ]]; then
  # Use Ollama to generate directives from custom keywords
  info "Generating directives from keywords via Ollama..."

  OLLAMA_HOST=$(grep "OLLAMA_HOST\|OLLAMA_BASE_URL" "$TEMPLATE_ROOT/backend/.env" 2>/dev/null \
    | head -1 | cut -d'=' -f2 | tr -d '"' || echo "http://192.168.1.185:11434")

  PROMPT="You are a JSON generator. Generate a directives.json file for an intelligence platform focused on: ${KEYWORDS}

Create 8-12 directives organized into topic groups. Each directive needs:
- name: descriptive name
- keywords: 15-25 relevant search keywords (specific terms, people, organizations, concepts)
- negative_keywords: []
- priority: number 10-98 (higher = more important)
- analysis_plan: [\"blue\", \"red\", \"purple\"]

Always include a catch-all directive named 'General News' with priority 10 and broad keywords.

Output ONLY valid JSON array. No preamble, no markdown fencing. Format:
[{\"topic\": \"Topic Name\", \"directives\": [{\"name\": \"...\", \"keywords\": [...], \"negative_keywords\": [], \"priority\": 90, \"analysis_plan\": [\"blue\",\"red\",\"purple\"]}]}]"

  RESPONSE=$(curl -sf "${OLLAMA_HOST}/api/generate" \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"gemma3:4b\", \"prompt\": $(echo "$PROMPT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'), \"stream\": false, \"options\": {\"temperature\": 0.3}}" \
    2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('response',''))" \
    2>/dev/null || echo "")

  if [[ -n "$RESPONSE" ]]; then
    # Extract JSON from response
    echo "$RESPONSE" | python3 -c "
import sys, json, re
text = sys.stdin.read()
# Try to find JSON array
match = re.search(r'\[.*\]', text, re.DOTALL)
if match:
    try:
        data = json.loads(match.group())
        print(json.dumps(data, indent=2))
    except:
        sys.exit(1)
else:
    sys.exit(1)
" > "$DIRECTIVES_FILE" 2>/dev/null && log "Directives generated via Ollama" \
    || warn "Ollama generation failed — falling back to $FOCUS preset"
  else
    warn "Ollama not responding — falling back to $FOCUS preset"
  fi
fi

# Fall back to focus preset if no keywords or Ollama failed
if [[ ! -s "$DIRECTIVES_FILE" ]] || ! python3 -m json.tool "$DIRECTIVES_FILE" &>/dev/null; then
  case "$FOCUS" in
    security)
      info "Using security preset directives"
      # Copy from huntaegis if available
      if [[ -f "/home/www/huntaegis_stack/backend/directives.json" ]]; then
        cp "/home/www/huntaegis_stack/backend/directives.json" "$DIRECTIVES_FILE"
        log "Security directives copied from huntaegis"
      else
        _write_security_directives "$DIRECTIVES_FILE"
      fi
      ;;
    social)
      info "Writing social/NEET directives"
      python3 - "$DIRECTIVES_FILE" << 'PYEOF'
import json, sys
data = [
  {"topic": "Youth Disengagement", "directives": [
    {"name": "NEET Indicators", "keywords": ["NEET", "not in education employment training", "youth unemployment", "disengaged youth", "disconnected youth", "idle youth", "youth inactivity", "school dropout", "early school leaving", "youth jobless"], "negative_keywords": [], "priority": 98, "analysis_plan": ["blue","red","purple"]},
    {"name": "Social Isolation", "keywords": ["social isolation", "loneliness epidemic", "social withdrawal", "hikikomori", "social anxiety", "atomization", "community breakdown", "disconnection", "alienation", "social exclusion", "belonging crisis"], "negative_keywords": [], "priority": 96, "analysis_plan": ["blue","red","purple"]},
    {"name": "Platform Addiction", "keywords": ["screen addiction", "social media addiction", "dopamine", "engagement trap", "algorithmic manipulation", "dark patterns", "attention economy", "infinite scroll", "outrage machine", "platform harm", "addictive design"], "negative_keywords": [], "priority": 95, "analysis_plan": ["blue","red","purple"]},
  ]},
  {"topic": "Corporate Disengagement Tactics", "directives": [
    {"name": "Predatory Engagement", "keywords": ["engagement bait", "ragebait", "outrage content", "viral manipulation", "manufactured controversy", "culture war content", "polarization", "division", "tribalism", "hate watch", "parasocial"], "negative_keywords": [], "priority": 94, "analysis_plan": ["blue","red","purple"]},
    {"name": "Economic Exclusion", "keywords": ["gig economy", "precarious work", "zero hours contract", "wage stagnation", "housing unaffordability", "cost of living", "economic anxiety", "financial precarity", "student debt", "generational poverty"], "negative_keywords": [], "priority": 93, "analysis_plan": ["blue","red","purple"]},
  ]},
  {"topic": "Pro-Social Interventions", "directives": [
    {"name": "Youth Employment Programs", "keywords": ["youth employment", "apprenticeship", "vocational training", "job guarantee", "youth scheme", "skills program", "mentorship", "career pathway", "work placement", "youth opportunity"], "negative_keywords": [], "priority": 90, "analysis_plan": ["blue","red","purple"]},
    {"name": "Community Building", "keywords": ["community resilience", "social cohesion", "neighborhood program", "civic engagement", "volunteering", "mutual aid", "third place", "community center", "public space", "belonging", "social infrastructure"], "negative_keywords": [], "priority": 88, "analysis_plan": ["blue","red","purple"]},
    {"name": "Mental Health Support", "keywords": ["youth mental health", "depression", "anxiety", "suicide prevention", "mental health crisis", "counseling access", "therapy", "wellbeing", "psychological safety", "crisis intervention"], "negative_keywords": [], "priority": 87, "analysis_plan": ["blue","red","purple"]},
  ]},
  {"topic": "Policy & Research", "directives": [
    {"name": "Youth Policy", "keywords": ["youth policy", "education reform", "welfare reform", "social safety net", "universal basic income", "housing policy", "youth homelessness", "child poverty", "inequality", "social mobility"], "negative_keywords": [], "priority": 85, "analysis_plan": ["blue","red","purple"]},
    {"name": "Research & Data", "keywords": ["youth research", "longitudinal study", "social science", "behavioral economics", "public health", "epidemiology", "statistics", "survey data", "policy evaluation", "evidence-based"], "negative_keywords": [], "priority": 83, "analysis_plan": ["blue","red","purple"]},
  ]},
  {"topic": "General", "directives": [
    {"name": "General Social News", "keywords": ["society", "social", "community", "youth", "young people", "generation", "culture", "welfare", "inequality", "poverty", "education", "employment", "health"], "negative_keywords": [], "priority": 10, "analysis_plan": ["blue","red","purple"]},
  ]},
]
json.dump(data, open(sys.argv[1], 'w'), indent=2)
print(f"Written {sum(len(t['directives']) for t in data)} directives")
PYEOF
      ;;
    finance)
      info "Writing finance directives"
      python3 - "$DIRECTIVES_FILE" << 'PYEOF'
import json, sys
data = [
  {"topic": "Markets", "directives": [
    {"name": "Equity Markets", "keywords": ["stock market", "S&P 500", "earnings", "IPO", "valuation", "bull market", "bear market", "volatility", "NYSE", "NASDAQ", "equity", "shares", "dividend"], "negative_keywords": [], "priority": 95, "analysis_plan": ["blue","red","purple"]},
    {"name": "Crypto & Digital Assets", "keywords": ["bitcoin", "ethereum", "cryptocurrency", "DeFi", "NFT", "blockchain", "stablecoin", "crypto regulation", "digital currency", "CBDC", "crypto exchange"], "negative_keywords": [], "priority": 90, "analysis_plan": ["blue","red","purple"]},
    {"name": "Macro & Central Banks", "keywords": ["Federal Reserve", "interest rates", "inflation", "CPI", "monetary policy", "quantitative easing", "recession", "GDP", "unemployment rate", "ECB", "Bank of England"], "negative_keywords": [], "priority": 98, "analysis_plan": ["blue","red","purple"]},
  ]},
  {"topic": "General", "directives": [
    {"name": "General Financial News", "keywords": ["finance", "economy", "market", "investment", "banking", "financial", "economic", "trade", "fiscal", "budget"], "negative_keywords": [], "priority": 10, "analysis_plan": ["blue","red","purple"]},
  ]},
]
json.dump(data, open(sys.argv[1], 'w'), indent=2)
PYEOF
      ;;
    health)
      info "Writing health directives"
      python3 - "$DIRECTIVES_FILE" << 'PYEOF'
import json, sys
data = [
  {"topic": "Public Health", "directives": [
    {"name": "Outbreak & Pandemic", "keywords": ["outbreak", "pandemic", "epidemic", "pathogen", "zoonotic", "WHO", "CDC", "disease surveillance", "R0", "transmission", "quarantine", "contact tracing"], "negative_keywords": [], "priority": 98, "analysis_plan": ["blue","red","purple"]},
    {"name": "Mental Health Crisis", "keywords": ["mental health", "depression", "anxiety", "suicide", "psychiatric", "therapy", "counseling", "addiction", "substance abuse", "overdose", "crisis"], "negative_keywords": [], "priority": 95, "analysis_plan": ["blue","red","purple"]},
    {"name": "Healthcare Policy", "keywords": ["healthcare", "NHS", "Medicare", "insurance", "drug pricing", "hospital", "access to care", "health equity", "pharmaceutical", "clinical trial", "FDA"], "negative_keywords": [], "priority": 90, "analysis_plan": ["blue","red","purple"]},
  ]},
  {"topic": "General", "directives": [
    {"name": "General Health News", "keywords": ["health", "medical", "disease", "treatment", "research", "clinical", "patient", "hospital", "doctor", "wellness"], "negative_keywords": [], "priority": 10, "analysis_plan": ["blue","red","purple"]},
  ]},
]
json.dump(data, open(sys.argv[1], 'w'), indent=2)
PYEOF
      ;;
    arts)
      info "Writing arts directives"
      python3 - "$DIRECTIVES_FILE" << 'PYEOF'
import json, sys
data = [
  {"topic": "Performing Arts", "directives": [
    {"name": "Dance & Choreography", "keywords": ["dance", "choreography", "ballet", "contemporary dance", "hip hop dance", "choreographer", "dance company", "performance", "movement", "dancer", "tour", "festival"], "negative_keywords": [], "priority": 95, "analysis_plan": ["blue","red","purple"]},
    {"name": "Theater & Stage", "keywords": ["theater", "theatre", "broadway", "west end", "play", "musical", "actor", "director", "production", "stage", "performance", "casting", "drama", "comedy"], "negative_keywords": [], "priority": 93, "analysis_plan": ["blue","red","purple"]},
    {"name": "Film & Screen", "keywords": ["film", "cinema", "movie", "director", "screenplay", "production", "streaming", "Hollywood", "Sundance", "Cannes", "box office", "studio", "casting"], "negative_keywords": [], "priority": 90, "analysis_plan": ["blue","red","purple"]},
  ]},
  {"topic": "General", "directives": [
    {"name": "General Arts News", "keywords": ["arts", "culture", "creative", "artist", "performance", "exhibition", "gallery", "museum", "award", "festival"], "negative_keywords": [], "priority": 10, "analysis_plan": ["blue","red","purple"]},
  ]},
]
json.dump(data, open(sys.argv[1], 'w'), indent=2)
PYEOF
      ;;
    *)
      info "Using general directives (copied from arc-codex)"
      cp "$TEMPLATE_ROOT/backend/directives.json" "$DIRECTIVES_FILE"
      ;;
  esac
fi

DIRECTIVE_COUNT=$(python3 -c "
import json
data = json.load(open('$DIRECTIVES_FILE'))
print(sum(len(t.get('directives',[])) for t in data))
" 2>/dev/null || echo "?")
log "directives.json ready ($DIRECTIVE_COUNT directives)"

# ── Create required directories ───────────────────────────────────────────────
step "📁 Creating directories"
mkdir -p "$STACK_ROOT/logs" "$STACK_ROOT/pids" "$STACK_ROOT/backups"
touch "$STACK_ROOT/logs/.gitkeep" "$STACK_ROOT/pids/.gitkeep"
log "Directories created"

# ── Create .gitignore ─────────────────────────────────────────────────────────
cat > "$STACK_ROOT/.gitignore" << 'EOF'
backend/.env
secret/
*.key
*.pem
backend/venv/
**/__pycache__/
*.pyc
frontend/node_modules/
frontend/.next/
logs/*.log
logs/*.log.gz
pids/
backups/
backend/upload/
backend/uploads/
*.tar.gz
*.zip
DOCKERENV
frontend/.env.local
frontend/.env
*.Mar*
*.faster
EOF
log ".gitignore written"

# ── Systemd unit ──────────────────────────────────────────────────────────────
step "🔧 Creating systemd unit"

UNIT_NAME="${SLUG}-stack"
sudo tee "/etc/systemd/system/${UNIT_NAME}.service" > /dev/null << EOF
[Unit]
Description=${NAME} Intelligence Stack
After=network-online.target redis.service docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=${STACK_USER}
WorkingDirectory=${STACK_ROOT}
ExecStart=${STACK_ROOT}/${SLUG}.sh start
ExecStop=${STACK_ROOT}/${SLUG}.sh stop
TimeoutStartSec=120
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "${UNIT_NAME}.service"
log "systemd unit ${UNIT_NAME}.service enabled"

# ── Git init ──────────────────────────────────────────────────────────────────
step "📦 Initializing git repo"

cd "$STACK_ROOT"
git init -q
git add .
git commit -q -m "${NAME} v1.0 — provisioned by provision.sh

- Focus: ${FOCUS}
- Domain: ${DOMAIN}
- Backend port: ${BACKEND_PORT}
- Frontend port: ${FRONTEND_PORT}
- Redis DB: ${REDIS_DB}
- Solr core: ${SOLR_CORE}"
log "Git repo initialized"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}✅ ${NAME} provisioned successfully!${NC}"
echo ""
echo -e "${CYAN}Stack root:${NC}    $STACK_ROOT"
echo -e "${CYAN}Domain:${NC}        $DOMAIN"
echo -e "${CYAN}Backend:${NC}       localhost:$BACKEND_PORT"
echo -e "${CYAN}Frontend:${NC}      localhost:$FRONTEND_PORT"
echo -e "${CYAN}Redis DB:${NC}      $REDIS_DB"
echo -e "${CYAN}Solr core:${NC}     $SOLR_CORE"
echo ""
echo -e "${BOLD}Next steps:${NC}"
echo ""
echo -e "  1. ${AMBER}Edit .env:${NC}"
echo -e "     nano $STACK_ROOT/backend/.env"
echo -e "     → Set BLUESKY_HANDLE, BLUESKY_APP_PASSWORD, NEXT_PUBLIC_BACKEND_URL=${DOMAIN}"
echo ""
echo -e "  2. ${AMBER}Add Caddy block:${NC}"
echo -e "     sudo nano /etc/caddy/Caddyfile"
echo -e "     → Add: ${DOMAIN} { handle /api/* { reverse_proxy localhost:${BACKEND_PORT} } handle { reverse_proxy localhost:${FRONTEND_PORT} } }"
echo ""
echo -e "  3. ${AMBER}Build and start:${NC}"
echo -e "     source $STACK_ROOT/${SLUG}_env.sh"
echo -e "     ${SLUG} build"
echo -e "     ${SLUG} start"
echo ""
echo -e "  4. ${AMBER}Enable Bluesky autopost:${NC}"
echo -e "     redis-cli -a \$REDIS_PASSWORD -n ${REDIS_DB} set bluesky:autopost 1"
echo ""
echo -e "  5. ${AMBER}Enable character commentary:${NC}"
echo -e "     redis-cli -a \$REDIS_PASSWORD -n ${REDIS_DB} set characters:enabled 1"
echo ""
echo -e "  6. ${AMBER}Push to GitHub:${NC}"
echo -e "     cd $STACK_ROOT"
echo -e "     git remote add origin https://github.com/hapnesbitt/${SLUG}.git"
echo -e "     git push -u origin main"
echo ""
