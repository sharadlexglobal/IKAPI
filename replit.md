# CourtCraft.ai - Indian Legal Search & Analysis

A web application for searching Indian legal judgments, laws, and tribunal orders using the Indian Kanoon API. Includes AI-powered Smart Search via Claude Haiku, judgment caching with PostgreSQL, most-cited sorting, and Gemini AI analysis.

## Project Structure

```
.
├── web/
│   ├── app.py              # Flask web server (port 5000)
│   ├── db.py               # PostgreSQL database layer
│   ├── gemini_service.py   # Gemini AI summarization service
│   ├── templates/
│   │   └── index.html       # Search + Analysis page template
│   └── static/
│       ├── style.css        # Styles
│       └── app.js           # Frontend logic (search, analysis, tabs)
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
- Document viewer overlay with "Cached" badge indicator
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

Indexes: `idx_judgments_cited_by` (DESC), `idx_judgments_publish_date`, `idx_search_queries_text`

## API Endpoints

- `GET /api/search?q=&page=&doctype=&fromdate=&todate=&sortby=` — Search documents (sortby supports mostcited)
- `GET /api/doc/<id>` — Fetch full document (returns from cache if available)
- `POST /api/save-doc/<id>` — Explicitly cache a document for analysis
- `POST /api/smart-search` — AI query conversion
- `GET /api/saved-queries` — List recent search queries with result counts
- `GET /api/query-judgments/<id>` — Get judgments linked to a saved query
- `GET /api/prompt-templates` — List all prompt templates
- `POST /api/prompt-templates` — Create template `{"name":"...","prompt_text":"..."}`
- `PUT /api/prompt-templates/<id>` — Update template
- `DELETE /api/prompt-templates/<id>` — Delete template
- `POST /api/analyze` — Gemini analysis `{"tids":[...],"prompt_template_id":1}` or `{"tids":[...],"custom_prompt":"..."}`

## Environment Variables

- `DATABASE_URL` — PostgreSQL connection string (auto-configured by Replit)
- `IK_API_TOKEN` — Indian Kanoon API token (stored as secret)
- `ANTHROPIC_API_KEY` — Anthropic API key for Claude Haiku Smart Search (stored as secret)
- `AI_INTEGRATIONS_GEMINI_BASE_URL` — Gemini API base URL (auto-configured by Replit AI Integrations)
- `AI_INTEGRATIONS_GEMINI_API_KEY` — Gemini API key placeholder (auto-configured by Replit AI Integrations)

## Dependencies

- **Python**: flask, gunicorn, beautifulsoup4, anthropic, psycopg2-binary, google-genai, tenacity
- **Java**: Maven project with argparse4j, json, opencsv, jsoup

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
- IK API calls have 15-second connection timeout and HTTP status validation
- Enter key is blocked during Smart Search loading via dedicated `isSmartSearchLoading` flag
- Smart Search resets all filter dropdowns before applying new values
- Python 3.12 required for google-genai package compatibility
