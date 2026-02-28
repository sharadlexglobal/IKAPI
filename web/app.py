import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import re
import json
import http.client
import urllib.parse
from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup
import anthropic
from db import (
    init_db, get_cached_judgment, save_judgment_metadata, save_judgment_full_text,
    save_search_query, get_saved_queries, get_judgments_for_query,
    get_judgments_by_tids, get_prompt_templates, save_prompt_template,
    update_prompt_template, delete_prompt_template, seed_default_templates
)
from gemini_service import summarize_judgments, estimate_tokens

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


def parse_publish_date(date_str):
    if not date_str:
        return None
    try:
        import datetime
        for fmt in ("%d %B, %Y", "%B %d, %Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                return datetime.datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
    except Exception:
        pass
    return None


def cache_search_results(docs, query_text, doctype, fromdate, todate, sortby, total):
    try:
        for doc in docs:
            tid = doc.get("tid")
            if tid:
                save_judgment_metadata(
                    tid=tid,
                    title=doc.get("title", "Untitled"),
                    doctype=doc.get("doctype", ""),
                    court_source=doc.get("docsource", ""),
                    publish_date=parse_publish_date(doc.get("publishdate", "")),
                    num_cites=doc.get("numcites", 0) or 0,
                    num_cited_by=doc.get("numcitedby", 0) or 0,
                )
        save_search_query(
            query_text=query_text,
            doctype_filter=doctype,
            from_date=fromdate,
            to_date=todate,
            sort_by=sortby,
            total_results=total,
            result_docs=docs,
        )
    except Exception as e:
        app.logger.warning(f"Failed to cache search results: {e}")


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

    if sortby and sortby not in ("mostrecent", "leastrecent", "mostcited"):
        return jsonify({"error": "Invalid sort option."}), 400

    if sortby == "mostcited":
        return _most_cited_search(q, doctype, fromdate, todate)

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
            cache_search_results(data["docs"], q, doctype, fromdate, todate, sortby, total)
        return jsonify(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _most_cited_search(q, doctype, fromdate, todate):
    form_input = q
    if doctype:
        form_input += f" doctypes: {doctype}"
    if fromdate:
        form_input += f" fromdate: {fromdate}"
    if todate:
        form_input += f" todate: {todate}"

    all_docs = {}
    real_total = 0

    try:
        for page in range(5):
            encoded = urllib.parse.quote_plus(form_input)
            url = f"/search/?formInput={encoded}&pagenum={page}"
            raw = call_ik_api(url)
            data = json.loads(raw)

            if page == 0:
                real_total = parse_total_from_found(data.get("found", ""))
                found_str = data.get("found", "")

            docs = data.get("docs", [])
            if not docs:
                break

            for doc in docs:
                tid = doc.get("tid")
                if tid and tid not in all_docs:
                    if "headline" in doc:
                        doc["headline"] = sanitize_html(doc["headline"])
                    if "title" in doc:
                        doc["title"] = sanitize_html(doc["title"])
                    all_docs[tid] = doc

        sorted_docs = sorted(
            all_docs.values(),
            key=lambda d: d.get("numcitedby", 0) or 0,
            reverse=True
        )
        top_docs = sorted_docs[:10]

        cache_search_results(list(all_docs.values()), q, doctype, fromdate, todate, "mostcited", real_total)

        return jsonify({
            "docs": top_docs,
            "found": found_str if real_total else "",
            "total": real_total,
            "mostcited_note": f"Sorted by most cited within top {len(all_docs)} results",
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/doc/<int:docid>")
def api_doc(docid):
    try:
        cached = get_cached_judgment(docid)
        if cached:
            return jsonify({
                "doc": cached["full_text_html"],
                "title": cached["title"],
                "cached": True,
            })
    except Exception as e:
        app.logger.warning(f"Cache lookup failed for {docid}: {e}")

    try:
        raw = call_ik_api(f"/doc/{docid}/")
        data = json.loads(raw)
        if "doc" in data:
            data["doc"] = sanitize_html(data["doc"])
        if "title" in data:
            data["title"] = sanitize_html(data["title"])

        try:
            save_judgment_full_text(docid, data.get("title", ""), data.get("doc", ""))
        except Exception as e:
            app.logger.warning(f"Failed to cache doc {docid}: {e}")

        data["cached"] = False
        return jsonify(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/save-doc/<int:docid>", methods=["POST"])
def api_save_doc(docid):
    try:
        cached = get_cached_judgment(docid)
        if cached:
            return jsonify({"success": True, "message": "Already cached"})
    except Exception:
        pass

    try:
        raw = call_ik_api(f"/doc/{docid}/")
        data = json.loads(raw)
        doc_html = sanitize_html(data.get("doc", ""))
        title = sanitize_html(data.get("title", ""))
        save_judgment_full_text(docid, title, doc_html)
        return jsonify({"success": True, "message": "Saved"})
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


@app.route("/api/saved-queries")
def api_saved_queries():
    try:
        queries = get_saved_queries()
        result = []
        for q in queries:
            result.append({
                "id": q["id"],
                "query_text": q["query_text"],
                "doctype_filter": q["doctype_filter"] or "",
                "total_results": q["total_results"] or 0,
                "result_count": q["result_count"],
                "searched_at": q["searched_at"].isoformat() if q["searched_at"] else "",
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/query-judgments/<int:query_id>")
def api_query_judgments(query_id):
    try:
        judgments = get_judgments_for_query(query_id)
        result = []
        for j in judgments:
            result.append({
                "tid": j["tid"],
                "title": j["title"] or "Untitled",
                "doctype": j["doctype"] or "",
                "court_source": j["court_source"] or "",
                "publish_date": j["publish_date"].isoformat() if j["publish_date"] else "",
                "num_cited_by": j["num_cited_by"] or 0,
                "has_full_text": not j["metadata_only"],
                "position": j["position"],
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/prompt-templates")
def api_get_templates():
    try:
        templates = get_prompt_templates()
        result = []
        for t in templates:
            result.append({
                "id": t["id"],
                "name": t["name"],
                "prompt_text": t["prompt_text"],
                "created_at": t["created_at"].isoformat() if t["created_at"] else "",
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/prompt-templates", methods=["POST"])
def api_create_template():
    body = request.get_json(silent=True)
    if not body or not body.get("name") or not body.get("prompt_text"):
        return jsonify({"error": "Name and prompt text are required"}), 400
    try:
        t = save_prompt_template(body["name"], body["prompt_text"])
        return jsonify({
            "id": t["id"],
            "name": t["name"],
            "prompt_text": t["prompt_text"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/prompt-templates/<int:tid>", methods=["PUT"])
def api_update_template(tid):
    body = request.get_json(silent=True)
    if not body or not body.get("name") or not body.get("prompt_text"):
        return jsonify({"error": "Name and prompt text are required"}), 400
    try:
        t = update_prompt_template(tid, body["name"], body["prompt_text"])
        if not t:
            return jsonify({"error": "Template not found"}), 404
        return jsonify({
            "id": t["id"],
            "name": t["name"],
            "prompt_text": t["prompt_text"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/prompt-templates/<int:tid>", methods=["DELETE"])
def api_delete_template(tid):
    try:
        deleted = delete_prompt_template(tid)
        if not deleted:
            return jsonify({"error": "Template not found"}), 404
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body is required"}), 400

    prompt_template_id = body.get("prompt_template_id")
    custom_prompt = body.get("custom_prompt", "")
    tids = body.get("tids", [])
    search_query_id = body.get("search_query_id")

    if not tids and not search_query_id:
        return jsonify({"error": "Provide tids or search_query_id"}), 400

    if not prompt_template_id and not custom_prompt:
        return jsonify({"error": "Provide prompt_template_id or custom_prompt"}), 400

    try:
        prompt_text = custom_prompt
        if prompt_template_id and not custom_prompt:
            templates = get_prompt_templates()
            tmpl = next((t for t in templates if t["id"] == prompt_template_id), None)
            if not tmpl:
                return jsonify({"error": "Template not found"}), 404
            prompt_text = tmpl["prompt_text"]

        if search_query_id and not tids:
            judgments = get_judgments_for_query(search_query_id)
            tids = [j["tid"] for j in judgments]

        if not tids:
            return jsonify({"error": "No judgments found"}), 400

        judgment_texts = []
        missing_tids = []
        existing = get_judgments_by_tids(tids)
        existing_map = {j["tid"]: j for j in existing}

        for tid in tids:
            j = existing_map.get(tid)
            if j and not j["metadata_only"] and j["full_text_html"]:
                soup = BeautifulSoup(j["full_text_html"], "html.parser")
                text = soup.get_text(separator="\n", strip=True)
                judgment_texts.append(f"[{j['title']}]\n{text}")
            else:
                missing_tids.append(tid)

        for tid in missing_tids:
            try:
                raw = call_ik_api(f"/doc/{tid}/")
                data = json.loads(raw)
                doc_html = sanitize_html(data.get("doc", ""))
                title = sanitize_html(data.get("title", ""))
                save_judgment_full_text(tid, title, doc_html)
                soup = BeautifulSoup(doc_html, "html.parser")
                text = soup.get_text(separator="\n", strip=True)
                judgment_texts.append(f"[{title}]\n{text}")
            except Exception as e:
                app.logger.warning(f"Failed to fetch doc {tid} for analysis: {e}")

        if not judgment_texts:
            return jsonify({"error": "Could not retrieve any judgment texts"}), 400

        total_chars = sum(len(t) for t in judgment_texts)
        estimated_tokens = total_chars // 4

        result = summarize_judgments(judgment_texts, prompt_text)

        return jsonify({
            "analysis": result,
            "judgments_analyzed": len(judgment_texts),
            "estimated_tokens": estimated_tokens,
        })
    except Exception as e:
        error_msg = str(e)
        if "FREE_CLOUD_BUDGET_EXCEEDED" in error_msg:
            return jsonify({"error": "Cloud budget exceeded. Please check your Replit credits."}), 402
        return jsonify({"error": error_msg}), 500


try:
    init_db()
    seed_default_templates()
except Exception as e:
    print(f"Warning: Could not initialize database: {e}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
