# CourtCraft.ai - Indian Legal Search & Analysis

A web application for searching Indian legal judgments, laws, and tribunal orders using the Indian Kanoon API. Includes AI-powered Smart Search via Claude Haiku, judgment caching with PostgreSQL, most-cited sorting, Gemini AI analysis, Genome Lab for deep judgment extraction, litigation research question generation, and an autonomous end-to-end research pipeline.

## Project Structure

```
.
├── web/
│   ├── app.py              # Flask web server (port 5000)
│   ├── db.py               # PostgreSQL database layer
│   ├── gemini_service.py   # Gemini AI summarization service
│   ├── genome_config.py    # Judgment Genome & Question Extractor prompts/config
│   ├── pipeline.py         # Pipeline orchestrator (7-step autonomous research)
│   ├── synthesis.py        # Dual-perspective research memo synthesis
│   ├── query_generator.py  # Question-to-IK-search-query converter
│   ├── cost_tracker.py     # Pipeline cost tracking (Claude API + IK API, USD/INR)
│   ├── topic_synthesis.py  # AI topic synthesis (evolution timeline, killer arguments)
│   ├── conflict_radar.py   # AI cross-topic conflict detection
│   ├── parallel_claude.py  # Async parallel Claude API calls (asyncio + AsyncAnthropic)
│   ├── expressway.py       # Superfast Expressway engine (instant legal research)
│   ├── expressway_prompts.py # Expressway prompt templates (query extraction + para drafting)
│   ├── genome_research.py  # Genome Research engine (discover genomes + generate reports)
│   ├── taxonomy_seed.py    # Taxonomy seed script (categories, topics, provisions)
│   ├── auto_tagger.py      # Auto-tagger engine (provision matching, keyword matching)
│   ├── templates/
│   │   └── index.html       # Search + Analysis + Genome Lab + Pipeline + District Court page
│   └── static/
│       ├── style.css        # Styles
│       ├── app.js           # Frontend logic (search, analysis, genome lab, pipeline)
│       ├── judgment_genome_schema_v3.1.json  # Genome JSON schema reference
│       ├── genome_master_prompt_v3.1.md     # Master LLM prompt for genome extraction (GPT/Claude/Gemini)
│       ├── genome_extraction_prompt.md      # Shorter extraction prompt (legacy)
│       └── genome_template_v3.1.json        # Filled JSON template example
├── python/
│   ├── ikapi.py             # Python CLI tool
│   └── requirements.txt     # Original requirements
├── java/
│   ├── pom.xml              # Maven build config (Java 19)
│   ├── run.sh               # Convenience shell script
│   └── src/                 # Java source code
├── search.sh                # Quick CLI search wrapper
└── data/                    # Downloaded results directory
```

## Web Frontend Features

### Search Tab
- Full-text search across Indian legal judgments via IK API
- Complete court/tribunal dropdown with 40+ courts grouped by category
- Filters by court type, date range (DD-MM-YYYY), and sort order (including Most Cited)
- Document viewer overlay with "Cached" badge indicator and "Extract Genome" button
- "Save for Analysis" button on search result cards
- Pagination using real total from API "found" string
- Collapsible search tips panel with all IK operators and 12 clickable example queries
- Claude Haiku AI Smart Search: converts natural language queries into precise IK search format

### Analysis Tab
- Select saved search queries to view associated judgments
- Checkbox selection of individual judgments for analysis
- Pre-built and custom prompt templates for Gemini AI
- CRUD management for prompt templates (New/Edit/Delete)
- Gemini AI analysis with formatted output and copy button
- Auto-fetches and caches full text for selected judgments if not already cached

### Genome Lab Tab
Four sub-tabs for deep legal analysis:

**Judgment Genome (Tab 1)**
- Extract structured 6-dimension genome from any judgment using Claude Sonnet 4
- Source: select from cached judgments dropdown OR paste judgment text
- "Extract Genome" button also available on document viewer for cached docs
- Genome viewer with 6 dimension tabs: Visible (teal), Structural (indigo), Invisible (amber), Weaponizable (coral), Synthesis (violet), Audit (cyan)
- Practitioner's Cheat Sheet shown first (cite_when, don't_cite_when, killer_paragraph, hidden_gem)
- Collapsible sections for each dimension with confidence badges (VERIFIED/SOUND_INFERENCE/SPECULATIVE/UNVERIFIED)
- Stress test blocks with verdict badges (INCLUDE/INCLUDE_WITH_CAVEAT/REMOVE)
- Certification level badge (COURT_USE/RESEARCH_USE_ONLY/DRAFT_REQUIRES_FURTHER_VERIFICATION)
- Durability score bar (0-10)
- Download genome as JSON
- Genomes cached in PostgreSQL (never re-extracted)

**Research Questions (Tab 2)**
- Extract 80-120 strategic research questions from litigation pleadings using Claude Sonnet 4
- Input: pleading text, pleading type dropdown (20 types), citation
- Gate questions highlighted at top (answer-these-first with if_favourable/if_unfavourable outcomes)
- Questions grouped by 14 categories with collapsible sections
- Each question shows: importance badge, perspective badge (ADVOCATE/OPPONENT/JUDGE), question type badge
- Sub-questions, fact anchors, research directions shown in expandable detail
- Hash-based caching (SHA256 of pleading text)
- Download questions as JSON

**Import Genome (Tab 3)**
- Manually paste genome JSON extracted from any external LLM (Gemini, GPT, etc.)
- Validates against v3.1 schema before saving (checks all 6 dimensions, extraction_metadata, required keys)
- Shows dimension-by-dimension validation status with section counts
- Fields: TID (optional, auto-generated), case title, court, extraction model
- Conflict detection: warns if genome already exists for TID, offers overwrite option
- Saves directly to PostgreSQL genome database
- API: POST /api/genome/validate, POST /api/genome/import

**Genome Database (Tab 4)**
- Searchable library of all stored genomes (49+ currently)
- Full-text search across case names and genome content (ILIKE on JSONB)
- Card grid view showing: case title, durability score, court, date, cited-by count
- Provisions displayed as tags (extracted from dimension_1)
- Core ratio decidendi preview on each card
- Model tag (claude-sonnet-4-6, manual-import, etc.) and extraction date
- Click any card to open full genome viewer with all 6 dimensions, cheat sheet, download
- API: GET /api/genome/database?q=search_term

**Taxonomy Browser (Tab 5)**
- Two-level taxonomy system: Categories (broad legal areas) → Topics (narrow legal issues)
- Categories sidebar with genome counts (e.g., "Negotiable Instruments Act, 1881" → 37 genomes)
- Click category → shows topics within it (e.g., "Service of Legal Notice" → 13 genomes, "Territorial Jurisdiction" → 11 genomes)
- Click topic → shows genome cards linked to that topic with durability scores and confidence badges
- Click genome card → opens full genome viewer in Genome Database tab
- Taxonomy search: search across categories, topics, provisions
- Re-tag All button: re-runs auto-tagger on all genomes
- Stats bar: total categories, topics, provisions, tagged/untagged genomes
- Auto-tagging: new genomes automatically tagged on save (extraction, pipeline, manual import)
- No AI calls — pure string matching against provision index and topic keywords
- 17 categories, 28 topics, 56 canonical provisions seeded from existing genome data
- **Coverage Dashboard**: Collapsible heatmap showing all topics color-coded by strength (STRONG/MODERATE/WEAK/GAP). Summary bar with topics covered, avg strength, gap count. Click any cell to navigate to that topic's genomes.
- **Topic Synthesis**: "Synthesize" button on each topic card. AI generates evolution timeline, settled propositions, open questions, killer arguments (petitioner + respondent), practice advisory. Cached in `topic_syntheses` table. Uses Claude Sonnet 4.
- **Genome Comparison**: Select 2-3 genomes via checkboxes → "Compare Selected" button → side-by-side view of ratio decidendi, provisions, sword/shield uses, vulnerability, cheat sheets.
- **Conflict Radar**: "Conflict Radar" button on each topic card. AI scans all genomes within a topic for contradictions (ratio conflicts, sword/shield conflicts, temporal shifts, hierarchy conflicts). Shows severity (HIGH/MEDIUM/LOW), resolution strategies, advocate actions. Cached in `conflict_scans` table. Uses Claude Sonnet 4.
- API: GET /api/taxonomy/categories, topics, provisions, search, genome tags, stats, heatmap; POST /api/taxonomy/retag, compare; GET/POST synthesis and conflict endpoints per topic

### District Court Tab (Judge Profiling)
- Delhi district courts: Saket, Patiala House, Tis Hazari, Rohini, Dwarka, Karkardooma (pre-seeded)
- Judge management: add judges per court with name and designation
- Order import: manually add court orders with case number, date, type (bail/interim/final/misc), parties, full text
- Orders table: paginated, sorted by date, with case type badges
- Judge Mind Map: placeholder for AI behavioral analysis (requires 10+ orders)
- Expandable to other cities (city selector in UI)
- API: GET /api/district/courts, judges, orders; POST /api/district/judges, orders; GET /api/district/judges/<id>/profile
- New files: `web/topic_synthesis.py` (topic synthesis AI), `web/conflict_radar.py` (conflict detection AI)

### Pipeline Tab (Autonomous Research)
Full end-to-end legal research pipeline. Submit a pleading and the system autonomously:

1. **Extracts Questions** — Claude Sonnet 4 generates 80-120 research questions from pleading
2. **Generates Queries** — Claude Haiku converts prioritized questions to IK search queries (batch 12)
3. **Searches IK** — Executes queries against Indian Kanoon API (3 pages / up to 30 results per query, 2s rate limit)
4. **Filters Relevance** — Claude Opus 4.6 with adaptive thinking scores each judgment 0-10 for relevance (streaming, batch 15, threshold 6.0)
5. **Fetches Documents** — Downloads full text for relevant judgments (max 35)
6. **Extracts Genomes** — Claude Sonnet 4 extracts 6-dimension genome per judgment
7. **Synthesizes Memo** — Claude Sonnet 4 produces dual-perspective research memo

**Pipeline Dashboard Features:**
- Job list with status badges and mini step progress bars
- Click-to-view detailed progress with animated step bar
- Real-time polling (5s interval) during active jobs
- Stats grid showing questions, queries, results, relevant judgments, genomes
- Error display with retry button for failed jobs
- Research memo viewer with advocate/opponent/judicial perspectives
- Issue-wise analysis, citation matrix, research gaps, action items
- Clickable judgment references (opens doc viewer)
- Submit pleading form with all case context fields
- Download memo as JSON

**Pipeline State Machine:**
```
RECEIVED → EXTRACTING_QUESTIONS → GENERATING_QUERIES → SEARCHING →
FILTERING → FETCHING_DOCS → EXTRACTING_GENOMES → SYNTHESIZING →
COMPLETED / FAILED
```

**Cost per run:** ~$20-70 (genome extraction is 80% of cost; cached genomes save significantly)

### Judgment Caching
- PostgreSQL database caches judgment metadata from search results
- Full document text cached on first view (avoids repeat IK API calls)
- Upsert strategy: never overwrites full text with metadata-only
- "Cached" badge shown when viewing previously-fetched documents

### Most-Cited Sorting
- Fetches 5 pages (50 results) from IK API, sorts by numcitedby desc
- Returns top 10 most-cited cases with disclaimer note
- All 50 fetched results get metadata cached as a bonus

## Database Schema (PostgreSQL)

- `judgments` — tid (PK), title, doctype, court_source, publish_date, num_cites, num_cited_by, full_text_html, metadata_only flag
- `search_queries` — logged search queries with filters and total results
- `search_query_results` — links queries to judgment tids with position
- `prompt_templates` — reusable Gemini prompt templates (3 defaults seeded)
- `judgment_genomes` — tid (FK→judgments, UNIQUE), genome_json (JSONB), schema_version, extraction_model, certification_level, overall_durability_score
- `question_extractions` — pleading_text_hash (UNIQUE), pleading_type, citation, questions_json (JSONB), question_count, extraction_model
- `research_jobs` — UUID PK, status, pleading_text, case context fields, step counters, research_memo (JSONB), cost_estimate_usd, cost_breakdown_json (JSONB), step timestamps
- `pipeline_queries` — job_id (FK), question_id, generated_ik_query, search_completed, results_count
- `pipeline_results` — job_id (FK), query_id (FK), tid, relevance_score, is_relevant, genome_extracted, UNIQUE(job_id, tid)
- `taxonomy_categories` — id TEXT PK (e.g., CAT_NI_ACT), name, parent_statute, description
- `taxonomy_topics` — id TEXT PK (e.g., TOP_NI138_NOTICE), category_id (FK), name, description, keywords TEXT[]
- `genome_categories` — genome_tid + category_id PK, auto_tagged BOOLEAN, many-to-many
- `genome_topics` — genome_tid + topic_id PK, auto_tagged BOOLEAN, confidence FLOAT, many-to-many
- `provision_index` — id TEXT PK (canonical, e.g., NI_ACT_S138), canonical_name, parent_statute, aliases TEXT[], category_id (FK)
- `topic_syntheses` — topic_id (FK), synthesis_json (JSONB), model, genome_count, created_at
- `conflict_scans` — topic_id, category_id, scan_json (JSONB), model, genome_count, created_at
- `district_courts` — id SERIAL PK, name, city, state, court_code UNIQUE, created_at
- `district_judges` — id SERIAL PK, name, designation, court_id (FK), active BOOLEAN, created_at
- `district_court_orders` — id SERIAL PK, judge_id (FK), court_id (FK), order_date, case_type, case_number, petitioner, respondent, order_text, tid (nullable), created_at
- `judge_genomes` — id SERIAL PK, judge_id (FK), order_id (FK), genome_json (JSONB), schema_version, extraction_model, extraction_date, durability_score
- `judge_profiles` — judge_id (FK, UNIQUE), profile_json (JSONB), total_orders_analyzed, last_updated, model_used

Indexes: `idx_judgments_cited_by` (DESC), `idx_judgments_publish_date`, `idx_search_queries_text`, `idx_genomes_tid`, `idx_research_jobs_status`, `idx_pipeline_queries_job`, `idx_pipeline_results_job`, `idx_pipeline_results_relevant`, `idx_taxonomy_topics_category`, `idx_taxonomy_topics_keywords` (GIN), `idx_genome_categories_cat`, `idx_genome_topics_topic`, `idx_provision_index_aliases` (GIN), `idx_provision_index_category`, `idx_dc_orders_judge`, `idx_dc_orders_court`, `idx_dc_orders_type`

## API Endpoints

### Search & Documents
- `GET /api/search?q=&page=&doctype=&fromdate=&todate=&sortby=` — Search documents (sortby supports mostcited)
- `GET /api/doc/<id>` — Fetch full document (returns from cache if available)
- `POST /api/save-doc/<id>` — Explicitly cache a document for analysis
- `POST /api/smart-search` — AI query conversion

### Analysis
- `GET /api/saved-queries` — List recent search queries with result counts
- `GET /api/query-judgments/<id>` — Get judgments linked to a saved query
- `GET /api/prompt-templates` — List all prompt templates
- `POST /api/prompt-templates` — Create template `{"name":"...","prompt_text":"..."}`
- `PUT /api/prompt-templates/<id>` — Update template
- `DELETE /api/prompt-templates/<id>` — Delete template
- `POST /api/analyze` — Gemini analysis `{"tids":[...],"prompt_template_id":1}` or `{"tids":[...],"custom_prompt":"..."}`

### Genome Lab
- `GET /api/cached-judgments` — List judgments with full text (for genome dropdown)
- `POST /api/genome/extract` — Extract genome `{"tid":int}` or `{"judgment_text":"...","citation":"..."}`
- `GET /api/genome/<tid>` — Get cached genome for a judgment
- `GET /api/genome/list` — List all extracted genomes with metadata
- `POST /api/questions/extract` — Extract research questions `{"pleading_text":"...","pleading_type":"WRIT_PETITION","citation":"..."}`

### Pipeline (Autonomous Research)
- `POST /api/pipeline/submit` — Submit pleading for research (returns job_id). Auth: `X-API-Key` header if PIPELINE_API_KEY env var set
- `GET /api/pipeline/status/<job_id>` — Get current pipeline status with step progress
- `GET /api/pipeline/result/<job_id>` — Get completed research memo
- `POST /api/pipeline/retry/<job_id>` — Resume failed pipeline from last step
- `GET /api/pipeline/list` — List all research jobs with metadata

### Taxonomy (Genome Cross-Linking)
- `GET /api/taxonomy/categories` — List categories with genome counts
- `GET /api/taxonomy/categories/<cat_id>/genomes` — List genomes in a category
- `GET /api/taxonomy/topics?category_id=` — List topics, optionally filtered by category
- `GET /api/taxonomy/topics/<topic_id>/genomes` — List genomes for a topic
- `GET /api/taxonomy/provisions` — List all canonical provisions with aliases
- `GET /api/taxonomy/search?q=` — Search across categories, topics, provisions
- `GET /api/taxonomy/genome/<tid>/tags` — Get category/topic tags for a genome
- `GET /api/taxonomy/stats` — Taxonomy overview stats
- `POST /api/taxonomy/retag` — Re-run auto-tagger on all genomes
- `GET /api/taxonomy/heatmap` — Coverage dashboard data (all topics with strength labels)
- `POST /api/taxonomy/topics/<topic_id>/synthesize` — AI topic synthesis (uses Claude Sonnet 4)
- `GET /api/taxonomy/topics/<topic_id>/synthesis` — Get cached topic synthesis
- `POST /api/taxonomy/compare` — Compare 2-3 genomes side-by-side `{"tids": [tid1, tid2]}`
- `POST /api/taxonomy/topics/<topic_id>/scan-conflicts` — AI conflict scan (uses Claude Sonnet 4)
- `GET /api/taxonomy/topics/<topic_id>/conflicts` — Get cached conflict scan

### District Court (Judge Profiling)
- `GET /api/district/courts?city=` — List courts by city
- `GET /api/district/courts/<court_id>/judges` — List judges for a court
- `GET /api/district/judges/<judge_id>` — Judge detail with stats
- `GET /api/district/judges/<judge_id>/orders?page=` — Paginated orders
- `POST /api/district/judges` — Add a judge `{"name":"...", "designation":"...", "court_id": int}`
- `POST /api/district/orders` — Import an order with full text
- `GET /api/district/judges/<judge_id>/profile` — Get cached judge profile

## Environment Variables

- `DATABASE_URL` — PostgreSQL connection string (auto-configured by Replit)
- `IK_API_TOKEN` — Indian Kanoon API token (stored as secret)
- `ANTHROPIC_API_KEY` — Anthropic API key for Claude (Smart Search + Genome Lab + Pipeline)
- `AI_INTEGRATIONS_GEMINI_BASE_URL` — Gemini API base URL (auto-configured by Replit AI Integrations)
- `AI_INTEGRATIONS_GEMINI_API_KEY` — Gemini API key placeholder (auto-configured by Replit AI Integrations)
- `PIPELINE_API_KEY` — Optional API key for pipeline webhook authentication

## Dependencies

- **Python**: flask, gunicorn, beautifulsoup4, anthropic, psycopg2-binary, google-genai, tenacity, requests, aiohttp
- **Java**: Maven project with argparse4j, json, opencsv, jsoup

## AI Models & Costs

- **Claude Haiku** (`claude-3-haiku-20240307`): Smart Search query conversion (~$0.001/query), pipeline query generation (~$0.001/batch)
- **Claude Opus 4.6** (`claude-opus-4-6`): Relevance filtering with adaptive thinking + streaming (~$0.03/batch of 15 judgments). Uses `thinking={"type": "adaptive"}` for deep legal reasoning on relevance scoring.
- **Claude Sonnet 4** (`claude-sonnet-4-6`): Genome extraction & question extraction (max_tokens=30000, timeout=600s, ~$0.50-2.00/extraction), synthesis (~$2-5/memo)
- **Gemini 2.5 Flash**: Analysis tab summarization (billed to Replit credits)

### Pipeline Cost Tracking

Real-time cost tracking implemented via `web/cost_tracker.py`. Costs are tracked per-step and updated to the database incrementally during pipeline execution. Exchange rate: **1 USD = 95 INR**.

**Claude API Pricing:**
| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| Claude 3 Haiku | $0.25 | $1.25 |
| Claude Opus 4.6 | $5.00 | $25.00 |
| Claude Sonnet 4 | $3.00 | $15.00 |

**IK API Pricing:**
| Request Type | Cost (INR) | Cost (USD) |
|-------------|-----------|-----------|
| Search | ₹0.50 | $0.0053 |
| Document | ₹0.20 | $0.0021 |
| Original Document | ₹0.50 | $0.0053 |
| Document Fragment | ₹0.05 | $0.0005 |
| Document Metainfo | ₹0.02 | $0.0002 |

**Estimated Cost Per Pipeline Run:**
| Step | Model/API | Estimated Cost |
|------|-----------|---------------|
| Question Extraction | Sonnet 4 | $1-2 |
| Query Generation | Haiku | $0.06 |
| IK Searches | IK API | ~$0.30 (60 searches) |
| Relevance Filtering | Opus 4.6 | $0.50-1.00 |
| Doc Fetching | IK API | ~$0.07 (35 docs) |
| Genome Extraction | Sonnet 4 | $15-60 |
| Synthesis | Sonnet 4 | $2-5 |
| **Total** | | **$20-70** |

Cost breakdown stored in `cost_breakdown_json` (JSONB) on each research job. Dashboard shows real-time cost with per-step details in both USD and INR.

## Integrations

- **Gemini AI**: Via Replit AI Integrations blueprint (python_gemini_ai_integrations). No separate API key needed — charges billed to Replit credits. Model: gemini-2.5-flash for analysis.
- **PostgreSQL**: Replit built-in PostgreSQL (Neon-backed), auto-provisioned via DATABASE_URL.

## Deployment

- Target: autoscale
- Run command: `gunicorn --bind=0.0.0.0:5000 --reuse-port web.app:app`

## Security

- Server-side HTML sanitization with BeautifulSoup (removes script, iframe, etc.)
- All error messages use DOM textContent to prevent XSS
- Input validation for dates (DD-MM-YYYY) and page numbers
- Smart Search validates doctype against whitelist, date format, and sort values
- Pipeline webhook: optional API key authentication via X-API-Key header
- Webhook callback: optional HMAC-SHA256 signature via X-Webhook-Signature header
- Pleading text minimum 200 characters, pleading_type validated against whitelist

## Pipeline Architecture Notes

- Pipeline runs as daemon thread (background processing)
- Each step is idempotent — re-running skips completed work
- Failed pipelines can resume from the failed step via retry endpoint
- MAX_QUESTIONS_TO_PROCESS=50, MAX_RELEVANT_JUDGMENTS=35, RELEVANCE_THRESHOLD=6.0
- IK API rate limit: 2s delay between requests
- Claude rate limit: exponential backoff on 429s
- Webhook callback: 3 retries with exponential backoff
- Genome extraction is the bottleneck (3-5 min per judgment x 35 judgments with rate limit retries)
- Genome extraction has retry logic: 2 retries with exponential backoff on timeout/connection errors
- JSON repair for truncated API responses: auto-detects max_tokens truncation and repairs JSON
- Question extraction limited to top 40 questions via prompt constraint (reduces output size)
- Caching is critical: cached genomes from prior runs save 80% of cost

### Research Tab (Genome-Based Legal Research)
New prominent tab that discovers relevant pre-analyzed judgment genomes from the database and generates comprehensive legal research reports.

**Discovery Algorithm (3-Layer):**
1. **Query Expansion (Haiku)** — Extracts keywords, provisions, legal concepts, taxonomy IDs from natural language question
2. **Multi-Signal DB Search** — Scores all genomes using 5 signals: taxonomy match (3pts), provision match (3pts), ratio match (2pts), weaponizable match (2pts), keyword match (1pt). Returns top 20 candidates.
3. **AI Relevance Filter (Haiku)** — Sends genome summaries + ratios to Haiku for relevance scoring (1-10). Keeps score >= 5.

**Report Generation (Single Sonnet call):**
- Extracts D1 (ratio, provisions, case identity), D4 (sword/shield, vulnerability), D5 (cheat sheet, summary) from relevant genomes
- Generates structured report: Executive Summary, Key Principles, Supporting Judgments, Contrary Positions, Practical Application, Strength Assessment

**API:**
- `POST /api/genome-research` — Full research `{question, max_genomes?}` → report + discovery stats
- `GET /api/genome-research/discover?q=` — Discovery only (no report, lightweight)

**Cost:** ~$0.10-$0.25 per query (no full text needed — reads from pre-extracted genomes)
**Files:** `web/genome_research.py` (engine)

### Superfast Expressway (Instant Legal Research)
Separate fast-track module that bypasses the full genome pipeline. Receives a pleading via webhook, finds relevant judgments, and returns ready-made legal paragraphs in 25-45 seconds.

**Flow:** Pleading → Claude Haiku generates 3-5 IK queries → Parallel IK search → Parallel doc fetch → Single Claude Sonnet call (1M context window) → 2-3 ready-made legal paragraphs

**Three outputs:**
1. Full judgment texts from IK API (code, no AI)
2. Relevant paragraphs + metadata (code, no AI)
3. Ready-made legal paragraphs citing accurate case titles, para numbers, holdings (one Claude Sonnet 4.6 call)

**API:**
- `POST /api/expressway/research` — Main endpoint. Auth: `X-API-Key`. Sync (blocks) or async (with callback_url)
- `GET /api/expressway/status/<job_id>` — Check async job status
- `GET /api/expressway/result/<job_id>` — Get completed result

**Request:** `{pleading_text, pleading_type?, court?, max_judgments? (default 15, max 25), callback_url?, webhook_secret?}`
**Response:** `{success, execution_time_seconds, queries_used[], full_texts[], relevant_extracts[], drafted_paragraphs, token_usage}`
**Cost:** ~$0.60-$1.50 per call (vs $20-70 for full pipeline)
**Files:** `web/expressway.py` (engine), `web/expressway_prompts.py` (prompts), `web/test_expressway.py` (test)
**DB table:** `expressway_jobs` — tracks async jobs with status, result, cost, token usage

## Notes

- Java compiler target set to 19 (from 21) to match Replit's GraalVM CE 22.3.1
- IK API uses POST requests for all endpoints; pagenum starts at 0
- Smart Search model: claude-3-haiku-20240307
- Smart Search uses single-quote strategy for phrase search in Claude's output
- Smart Search has 3-layer JSON fallback: (1) direct parse, (2) double-quote fix, (3) regex field extraction
- IK API calls have 30-second connection timeout and HTTP status validation
- Enter key is blocked during Smart Search loading via dedicated `isSmartSearchLoading` flag
- Smart Search resets all filter dropdowns before applying new values
- Python 3.12 required for google-genai package compatibility
- Genome extraction uses Claude Sonnet 4 with 6-dimension schema (v3.1.0) — prompts in genome_config.py
- Question extraction uses hash-based caching (SHA256 of pleading text, first 32 hex chars)
- Pipeline orchestrator imports from app.py (call_ik_api, sanitize_html) — avoid circular imports by using lazy imports
