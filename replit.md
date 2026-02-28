# IKAPI - Indian Kanoon API Tools

A toolkit for accessing the [Indian Kanoon](https://api.indiankanoon.org) legal database API. Includes a web frontend, plus CLI tools in Python and Java.

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

## Web Frontend

The main application is a Flask web app serving on port 5000. It provides:
- Full-text search across Indian legal judgments
- Filters by court type, date range, and sort order
- Document viewer overlay for reading full judgments
- Pagination through results

## Environment Variables

- `IK_API_TOKEN` - Indian Kanoon API token (stored as secret)

## Dependencies

- **Python**: flask, gunicorn, beautifulsoup4 (managed via uv/pyproject.toml)
- **Java**: Maven project with argparse4j, json, opencsv, jsoup

## Deployment

- Target: autoscale
- Run command: `gunicorn --bind=0.0.0.0:5000 --reuse-port web.app:app`

## CLI Usage

```bash
./search.sh "right to information"
python python/ikapi.py -s $IK_API_TOKEN -D ./data -q "your query"
java -jar java/target/ikapi-1.0.0.jar -s $IK_API_TOKEN -D ./data -q "your query"
```

## Notes

- Java compiler target set to 19 (from 21) to match Replit's GraalVM CE 22.3.1
