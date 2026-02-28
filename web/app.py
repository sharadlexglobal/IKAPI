import os
import re
import json
import http.client
import urllib.parse
from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup
import anthropic

app = Flask(__name__)

API_HOST = "api.indiankanoon.org"

UNSAFE_TAGS = {"script", "style", "iframe", "object", "embed", "form", "input", "textarea", "button", "link", "meta"}

DATE_PATTERN = re.compile(r"^\d{1,2}-\d{1,2}-\d{4}$")


def is_valid_date(date_str):
    if not DATE_PATTERN.match(date_str):
        return False
    parts = date_str.split("-")
    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
    if month < 1 or month > 12:
        return False
    if day < 1 or day > 31:
        return False
    if month in (4, 6, 9, 11) and day > 30:
        return False
    if month == 2:
        leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
        if day > (29 if leap else 28):
            return False
    return True

VALID_DOCTYPES = {
    "", "supremecourt", "judgments", "highcourts", "tribunals", "laws",
    "delhi", "bombay", "kolkata", "chennai", "allahabad", "andhra",
    "chattisgarh", "gauhati", "jammu", "srinagar", "kerala", "lucknow",
    "orissa", "uttaranchal", "gujarat", "himachal_pradesh", "jharkhand",
    "karnataka", "madhyapradesh", "patna", "punjab", "rajasthan", "sikkim",
    "kolkata_app", "jodhpur", "patna_orders", "meghalaya",
    "delhidc",
    "aptel", "drat", "cat", "cegat", "stt", "itat", "consumer", "cerc",
    "cic", "clb", "copyrightboard", "ipab", "mrtp", "sebisat", "tdsat",
    "trademark", "greentribunal", "cci",
}

SMART_SEARCH_SYSTEM = """You are a legal search query formatter for Indian Kanoon (indiankanoon.org), India's largest legal database.

Your job: Convert the user's natural language query into a precise Indian Kanoon search query.

SEARCH SYNTAX RULES:
- Phrase search: wrap in single quotes, e.g. 'freedom of speech' (the system converts them to double quotes)
- AND: use ANDD (case sensitive, with spaces), e.g. murder ANDD kidnapping. Multiple words without operators are implicitly AND.
- OR: use ORR (case sensitive, with spaces), e.g. murder ORR kidnapping
- NOT: use ANDD NOTT (case sensitive), e.g. murder ANDD NOTT kidnapping
- Title filter: title: word_or_phrase
- Author/Judge filter: author: judge_name
- Bench filter: bench: judge_name
- Citation filter: cite: citation_string

AVAILABLE DOCTYPES (court filters):
- supremecourt, delhi, bombay, kolkata, chennai, allahabad, andhra, chattisgarh, gauhati, jammu, srinagar, kerala, lucknow, orissa, uttaranchal, gujarat, himachal_pradesh, jharkhand, karnataka, madhyapradesh, patna, punjab, rajasthan, sikkim, kolkata_app, jodhpur, patna_orders, meghalaya
- District courts: delhidc
- Tribunals: aptel, drat, cat, cegat, stt, itat, consumer, cerc, cic, clb, copyrightboard, ipab, mrtp, sebisat, tdsat, trademark, greentribunal, cci
- Aggregators: judgments (all courts), highcourts (all HCs), tribunals (all tribunals), laws (acts & rules)

SORT OPTIONS: mostrecent, leastrecent

JSON SCHEMA (you must respond with ONLY this JSON structure, no markdown, no explanation, no backticks):
{
  "query": "<formatted IK search query string using operators above>",
  "doctype": "<one of the AVAILABLE DOCTYPES above, or empty string>",
  "fromdate": "<DD-MM-YYYY or empty string>",
  "todate": "<DD-MM-YYYY or empty string>",
  "sortby": "<mostrecent or leastrecent or empty string>"
}

CRITICAL RULES:
1. ALL five fields are REQUIRED in every response. Use "" for fields that don't apply.
2. For phrase search inside the "query" value, ALWAYS use SINGLE QUOTES, never double quotes. Example: 'right to privacy' not "right to privacy". The system converts single quotes to double quotes automatically.
3. Do NOT put inline filters (doctypes:, fromdate:, todate:, sortby:) inside the "query" field. Put them in their dedicated JSON fields.
4. Extract the LEGAL CONCEPTS from the user's query. Do not pass the user's full sentence as the query.
5. The "doctype" value must exactly match one from the AVAILABLE DOCTYPES list, or be "".

JSON SCHEMA (repeated for emphasis):
{
  "query": "<formatted IK search query string>",
  "doctype": "<doctype or empty string>",
  "fromdate": "<DD-MM-YYYY or empty string>",
  "todate": "<DD-MM-YYYY or empty string>",
  "sortby": "<mostrecent or leastrecent or empty string>"
}

EXAMPLES:

User: "show me supreme court cases about right to privacy"
{"query": "'right to privacy'", "doctype": "supremecourt", "fromdate": "", "todate": "", "sortby": ""}

User: "cases by justice chandrachud on fundamental rights from 2020"
{"query": "'fundamental rights' author: chandrachud", "doctype": "", "fromdate": "01-01-2020", "todate": "", "sortby": ""}

User: "latest bombay high court orders on bail in NDPS cases"
{"query": "bail ANDD 'NDPS Act'", "doctype": "bombay", "fromdate": "", "todate": "", "sortby": "mostrecent"}

User: "land acquisition cases but not government land"
{"query": "'land acquisition' ANDD NOTT 'government land'", "doctype": "", "fromdate": "", "todate": "", "sortby": ""}

User: "section 498a or domestic violence cases in delhi"
{"query": "'section 498a' ORR 'domestic violence'", "doctype": "delhi", "fromdate": "", "todate": "", "sortby": ""}

User: "NGT orders on pollution in 2023"
{"query": "pollution", "doctype": "greentribunal", "fromdate": "01-01-2023", "todate": "31-12-2023", "sortby": ""}

User: "ITAT rulings on capital gains"
{"query": "'capital gains'", "doctype": "itat", "fromdate": "", "todate": "", "sortby": ""}

User: "consumer court cases about defective products"
{"query": "'defective products'", "doctype": "consumer", "fromdate": "", "todate": "", "sortby": ""}

User: "Registrar of DRAT dismissed section 21 waiver application and order is void ab initio"
{"query": "'section 21' ANDD 'waiver application' ANDD 'void ab initio' ANDD 'Registrar'", "doctype": "drat", "fromdate": "", "todate": "", "sortby": ""}

User: "children's rights cases in supreme court about education"
{"query": "'right to education' ANDD children", "doctype": "supremecourt", "fromdate": "", "todate": "", "sortby": ""}

User: "all high court cases about anticipatory bail in murder from 2015 to 2023 latest first"
{"query": "'anticipatory bail' ANDD murder", "doctype": "highcourts", "fromdate": "01-01-2015", "todate": "31-12-2023", "sortby": "mostrecent"}

User: "competition commission orders against cartels"
{"query": "cartel ORR 'anti-competitive agreement'", "doctype": "cci", "fromdate": "", "todate": "", "sortby": ""}

REMEMBER: Respond with ONLY valid JSON. Use single quotes for phrases inside "query". All 5 fields required. Extract legal concepts, do not pass raw user text."""


def get_api_token():
    token = os.environ.get("IK_API_TOKEN", "")
    if not token:
        raise ValueError("IK_API_TOKEN is not configured. Please set it in Replit Secrets.")
    return token


def sanitize_html(html_str):
    if not html_str:
        return html_str
    soup = BeautifulSoup(html_str, "html.parser")
    for tag in soup.find_all(UNSAFE_TAGS):
        tag.decompose()
    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr.startswith("on") or attr in ("srcdoc", "action"):
                del tag[attr]
            elif attr in ("href", "src") and tag.get(attr, "").strip().lower().startswith("javascript:"):
                del tag[attr]
    return str(soup)


def call_ik_api(url):
    token = get_api_token()
    headers = {
        "Authorization": f"Token {token}",
        "Accept": "application/json",
    }
    connection = http.client.HTTPSConnection(API_HOST, timeout=15)
    try:
        connection.request("POST", url, headers=headers)
        response = connection.getresponse()
        status = response.status
        data = response.read()
        if isinstance(data, bytes):
            data = data.decode("utf8")
        if status >= 400:
            raise Exception(f"Indian Kanoon API returned error ({status})")
        return data
    finally:
        connection.close()


def parse_total_from_found(found_str):
    if not found_str:
        return 0
    match = re.search(r"of\s+([\d,]+)", found_str)
    if match:
        return int(match.group(1).replace(",", ""))
    return 0


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    page_str = request.args.get("page", "0")
    doctype = request.args.get("doctype", "").strip()
    fromdate = request.args.get("fromdate", "").strip()
    todate = request.args.get("todate", "").strip()
    sortby = request.args.get("sortby", "").strip()

    if not q:
        return jsonify({"error": "Query is required"}), 400

    try:
        page = max(0, int(page_str))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid page number"}), 400

    if fromdate and not is_valid_date(fromdate):
        return jsonify({"error": "Invalid from date. Use a valid date in DD-MM-YYYY format."}), 400

    if todate and not is_valid_date(todate):
        return jsonify({"error": "Invalid to date. Use a valid date in DD-MM-YYYY format."}), 400

    if doctype and doctype not in VALID_DOCTYPES:
        return jsonify({"error": "Invalid court/document type."}), 400

    if sortby and sortby not in ("mostrecent", "leastrecent"):
        return jsonify({"error": "Invalid sort option."}), 400

    form_input = q
    if doctype:
        form_input += f" doctypes: {doctype}"
    if fromdate:
        form_input += f" fromdate: {fromdate}"
    if todate:
        form_input += f" todate: {todate}"
    if sortby:
        form_input += f" sortby: {sortby}"

    encoded = urllib.parse.quote_plus(form_input)
    url = f"/search/?formInput={encoded}&pagenum={page}"

    try:
        raw = call_ik_api(url)
        data = json.loads(raw)
        total = parse_total_from_found(data.get("found", ""))
        data["total"] = total
        if "docs" in data:
            for doc in data["docs"]:
                if "headline" in doc:
                    doc["headline"] = sanitize_html(doc["headline"])
                if "title" in doc:
                    doc["title"] = sanitize_html(doc["title"])
        return jsonify(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/doc/<int:docid>")
def api_doc(docid):
    try:
        raw = call_ik_api(f"/doc/{docid}/")
        data = json.loads(raw)
        if "doc" in data:
            data["doc"] = sanitize_html(data["doc"])
        if "title" in data:
            data["title"] = sanitize_html(data["title"])
        return jsonify(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/smart-search", methods=["POST"])
def api_smart_search():
    body = request.get_json(silent=True)
    if not body or not body.get("query", "").strip():
        return jsonify({"error": "Query is required"}), 400

    user_query = body["query"].strip()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY is not configured."}), 503

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=300,
            system=SMART_SEARCH_SYSTEM,
            messages=[
                {"role": "user", "content": user_query}
            ]
        )

        response_text = message.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.strip("`").strip()
            if response_text.startswith("json"):
                response_text = response_text[4:].strip()

        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            fixed = re.sub(r'""([^"]+)""', r'"\1"', response_text)
            try:
                result = json.loads(fixed)
            except json.JSONDecodeError:
                query_match = re.search(r'"query"\s*:\s*"(.*?)"(?=\s*,\s*"(?:doctype|fromdate|todate|sortby)"|$)', response_text, re.DOTALL)
                doctype_match = re.search(r'"doctype"\s*:\s*"([^"]*)"', response_text)
                fromdate_match = re.search(r'"fromdate"\s*:\s*"([^"]*)"', response_text)
                todate_match = re.search(r'"todate"\s*:\s*"([^"]*)"', response_text)
                sortby_match = re.search(r'"sortby"\s*:\s*"([^"]*)"', response_text)
                result = {
                    "query": query_match.group(1) if query_match else user_query,
                    "doctype": doctype_match.group(1) if doctype_match else "",
                    "fromdate": fromdate_match.group(1) if fromdate_match else "",
                    "todate": todate_match.group(1) if todate_match else "",
                    "sortby": sortby_match.group(1) if sortby_match else "",
                }

        query_text = result.get("query", user_query)
        query_text = re.sub(r"'([^']+)'", r'"\1"', query_text)

        doctype = result.get("doctype", "")
        if doctype not in VALID_DOCTYPES:
            doctype = ""

        fromdate = result.get("fromdate", "")
        if fromdate and not is_valid_date(fromdate):
            fromdate = ""

        todate = result.get("todate", "")
        if todate and not is_valid_date(todate):
            todate = ""

        sortby = result.get("sortby", "")
        if sortby not in ("mostrecent", "leastrecent", ""):
            sortby = ""

        return jsonify({
            "query": query_text,
            "doctype": doctype,
            "fromdate": fromdate,
            "todate": todate,
            "sortby": sortby,
        })
    except json.JSONDecodeError as e:
        app.logger.warning(f"Smart search JSON parse error: {e}. Raw: {response_text!r}")
        return jsonify({"query": user_query, "doctype": "", "fromdate": "", "todate": "", "sortby": ""})
    except anthropic.APIError as e:
        return jsonify({"error": f"AI service error: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
