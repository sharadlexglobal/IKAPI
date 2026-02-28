# IKAPI - Indian Kanoon API Tools

A CLI toolkit for accessing the [Indian Kanoon](https://api.indiankanoon.org) legal database API. Available in both Python and Java.

## Project Structure

```
.
├── python/
│   ├── ikapi.py          # Python CLI tool
│   └── requirements.txt  # Python dependencies (beautifulsoup4)
└── java/
    ├── pom.xml           # Maven build config (Java 19)
    ├── run.sh            # Convenience shell script
    └── src/
        └── main/java/org/indiankanoon/
            └── IKApiMain.java
```

## Setup

### Python
Dependencies are installed via `uv` (beautifulsoup4).

```bash
python python/ikapi.py --help
```

### Java
Built with Maven. The JAR is pre-compiled at `java/target/ikapi-1.0.0.jar`.

```bash
java -jar java/target/ikapi-1.0.0.jar --help
# or
cd java && ./run.sh --help
```

## Usage

Both tools require an Indian Kanoon API token (`-s TOKEN`) and a data directory (`-D DATADIR`).

Example:
```bash
python python/ikapi.py -s YOUR_TOKEN -D ./data -q "right to information"
```

## Notes

- Java compiler target was set to 19 (from 21) to match the available GraalVM CE 22.3.1 (Java 19) runtime in Replit.
- This is a pure CLI tool — no web frontend or server component.
