# IKAPI - Indian Legal Search

A web application for searching Indian legal judgments, laws, and tribunal orders using the Indian Kanoon API. Includes AI-powered Smart Search via Claude Haiku.

## Project Structure

```
.
├── web/
│   ├── app.py              # Flask web server (port 5000)
│   ├── templates/
│   │   └── index.html       # Search page template
│   └── static/
│       ├── style.css        # Styles
│       └── app.js           # Frontend search logic
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

- Full-text search across Indian legal judgments via IK API
- Complete court/tribunal dropdown with 40+ courts grouped by category (Supreme Court, High Courts, District Courts, Tribunals, Aggregators) using `<optgroup>`
- Filters by court type, date range (DD-MM-YYYY), and sort order
- Document viewer overlay for reading full judgments (with scroll lock)
- Pagination using real total from API "found" string
- Collapsible search tips panel with all IK operators and 12 clickable example queries
- Claude Haiku AI Smart Search: converts natural language queries into precise IK search format, pre-fills search box and filter dropdowns

## API Endpoints

- `GET /api/search?q=&page=&doctype=&fromdate=&todate=&sortby=` - Search documents
- `GET /api/doc/<id>` - Fetch full document by ID
- `POST /api/smart-search` - AI query conversion (accepts `{"query": "natural language"}`, returns `{query, doctype, fromdate, todate, sortby}`)

## Environment Variables

- `IK_API_TOKEN` - Indian Kanoon API token (stored as secret)
- `ANTHROPIC_API_KEY` - Anthropic API key for Claude Haiku Smart Search (stored as secret)

## Dependencies

- **Python**: flask, gunicorn, beautifulsoup4, anthropic (managed via uv/pyproject.toml)
- **Java**: Maven project with argparse4j, json, opencsv, jsoup

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
- Smart Search uses single-quote strategy for phrase search in Claude's output (avoids JSON parse issues with nested double quotes), converts balanced single-quoted phrases back to double quotes via regex before returning
- Smart Search has 3-layer JSON fallback: (1) direct parse, (2) double-quote fix, (3) regex field extraction
- IK API calls have 15-second connection timeout and HTTP status validation (raises on 4xx/5xx)
- Enter key is blocked during Smart Search loading via dedicated `isSmartSearchLoading` flag
- Smart Search resets all filter dropdowns before applying new values (prevents stale filters from previous queries)
