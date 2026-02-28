# CourtCraft.ai - Indian Legal Search & Analysis

A web application for searching Indian legal judgments, laws, and tribunal orders using the Indian Kanoon API. Includes AI-powered Smart Search via Claude Haiku, judgment caching with PostgreSQL, most-cited sorting, Gemini AI analysis, and the Genome Lab for deep judgment extraction and litigation research question generation.

## Project Structure

```
.
├── web/
│   ├── app.py              # Flask web server (port 5000)
│   ├── db.py               # PostgreSQL database layer
│   ├── gemini_service.py   # Gemini AI summarization service
│   ├── genome_config.py    # Judgment Genome & Question Extractor prompts/config
│   ├── templates/
│   │   └── index.html       # Search + Analysis + Genome Lab page template
│   └── static/
│       ├── style.css        # Styles
│       ├── app.js           # Frontend logic (search, analysis, genome lab)
│       └── judgment_genome_schema_v3.1.json  # Genome JSON schema reference
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
Two sub-tabs for deep legal analysis:

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
- `judgment_genomes` — tid (FK→judgments, UNIQUE), genome_json (JSONB), schema_version, extraction_model, extraction_date, document_id, certification_level, overall_durability_score
- `question_extractions` — pleading_text_hash (UNIQUE), pleading_type, citation, questions_json (JSONB), question_count, extraction_model, extracted_at

Indexes: `idx_judgments_cited_by` (DESC), `idx_judgments_publish_date`, `idx_search_queries_text`, `idx_genomes_tid`

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

## Environment Variables

- `DATABASE_URL` — PostgreSQL connection string (auto-configured by Replit)
- `IK_API_TOKEN` — Indian Kanoon API token (stored as secret)
- `ANTHROPIC_API_KEY` — Anthropic API key for Claude (Smart Search + Genome Lab)
- `AI_INTEGRATIONS_GEMINI_BASE_URL` — Gemini API base URL (auto-configured by Replit AI Integrations)
- `AI_INTEGRATIONS_GEMINI_API_KEY` — Gemini API key placeholder (auto-configured by Replit AI Integrations)

## Dependencies

- **Python**: flask, gunicorn, beautifulsoup4, anthropic, psycopg2-binary, google-genai, tenacity
- **Java**: Maven project with argparse4j, json, opencsv, jsoup

## AI Models & Costs

- **Claude Haiku** (`claude-3-haiku-20240307`): Smart Search query conversion (~$0.001/query)
- **Claude Sonnet 4** (`claude-sonnet-4-20250514`): Genome extraction & question extraction (max_tokens=30000, timeout=300s, ~$0.50-2.00/extraction)
- **Gemini 2.5 Flash**: Analysis tab summarization (billed to Replit credits)

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
