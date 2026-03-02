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
import hashlib
from db import (
    init_db, get_cached_judgment, save_judgment_metadata, save_judgment_full_text,
    save_search_query, get_saved_queries, get_judgments_for_query,
    get_judgments_by_tids, get_prompt_templates, save_prompt_template,
    update_prompt_template, delete_prompt_template, seed_default_templates,
    get_cached_genome, save_genome, get_all_genomes, get_all_genomes_rich,
    search_genomes, ensure_judgment_exists,
    get_cached_judgments_with_fulltext,
    save_question_extraction, get_question_extraction,
    create_research_job, get_research_job, update_research_job,
    get_all_research_jobs, get_pipeline_queries, get_pipeline_results,
    get_all_taxonomy_categories, get_taxonomy_topics,
    get_genomes_for_category, get_genomes_for_topic,
    get_all_provisions, search_taxonomy, get_genome_tags,
    get_taxonomy_stats,
    get_coverage_heatmap, get_topic_genomes_with_json,
    get_topic_synthesis, get_genomes_for_comparison,
    get_conflict_scan,
    get_district_courts, get_district_judges, get_district_judge,
    add_district_judge, add_district_order, get_district_orders,
    get_judge_profile, get_fetched_dc_judgments,
)
from gemini_service import summarize_judgments, estimate_tokens
from genome_config import (
    APIConfig, build_master_prompt, get_schema_summary,
    strip_markdown_fences, build_question_extractor_prompt,
    get_question_schema_summary
)

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s", stream=sys.stderr)

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
    connection = http.client.HTTPSConnection(API_HOST, timeout=30)
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


@app.route("/api/cached-judgments")
def api_cached_judgments():
    try:
        judgments = get_cached_judgments_with_fulltext()
        result = []
        for j in judgments:
            result.append({
                "tid": j["tid"],
                "title": j["title"] or "Untitled",
                "doctype": j["doctype"] or "",
                "court_source": j["court_source"] or "",
                "publish_date": j["publish_date"].isoformat() if j["publish_date"] else "",
                "num_cited_by": j["num_cited_by"] or 0,
                "fetched_at": j["fetched_at"].isoformat() if j["fetched_at"] else "",
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/genome/extract", methods=["POST"])
def api_genome_extract():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body is required"}), 400

    tid = body.get("tid")
    judgment_text = body.get("judgment_text", "").strip()
    citation = body.get("citation", "")

    if not tid and not judgment_text:
        return jsonify({"error": "Provide tid (cached judgment) or judgment_text"}), 400

    if not APIConfig.is_configured():
        return jsonify({"error": "ANTHROPIC_API_KEY is not configured"}), 503

    try:
        if tid:
            cached_genome = get_cached_genome(tid)
            if cached_genome:
                genome_data = cached_genome["genome_json"]
                if isinstance(genome_data, str):
                    genome_data = json.loads(genome_data)
                return jsonify({
                    "genome": genome_data,
                    "cached": True,
                    "tid": tid,
                    "extraction_date": cached_genome["extraction_date"].isoformat() if cached_genome["extraction_date"] else "",
                })

            cached_doc = get_cached_judgment(tid)
            if not cached_doc:
                return jsonify({"error": "Judgment not found in cache. View it first to cache it."}), 404
            soup = BeautifulSoup(cached_doc["full_text_html"], "html.parser")
            judgment_text = soup.get_text(separator="\n", strip=True)
            citation = cached_doc.get("title", "") or citation

        text_len = len(judgment_text)
        if text_len < APIConfig.MIN_JUDGMENT_LENGTH:
            return jsonify({"error": f"Judgment text too short ({text_len} chars). Minimum {APIConfig.MIN_JUDGMENT_LENGTH} required."}), 400
        if text_len > APIConfig.MAX_JUDGMENT_LENGTH:
            return jsonify({"error": f"Judgment text too long ({text_len} chars). Maximum {APIConfig.MAX_JUDGMENT_LENGTH} allowed."}), 400

        system_prompt = build_master_prompt()
        schema_summary = get_schema_summary()

        user_message = f"## SCHEMA SUMMARY\n{schema_summary}\n\n## JUDGMENT TEXT\n\nCitation: {citation}\n\n{judgment_text}"

        client = anthropic.Anthropic(api_key=APIConfig.api_key())
        message = client.messages.create(
            model=APIConfig.model(),
            max_tokens=APIConfig.max_tokens(),
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            timeout=APIConfig.timeout(),
        )

        response_text = message.content[0].text
        cleaned = strip_markdown_fences(response_text)

        try:
            genome_data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            app.logger.error(f"Genome JSON parse failed: {e}. First 500 chars: {cleaned[:500]}")
            return jsonify({"error": "Failed to parse genome output as JSON. The model may have returned invalid JSON."}), 422

        doc_id = genome_data.get("document_id", "")
        cert_level = None
        durability = None
        try:
            cert_level = genome_data.get("dimension_6_audit", {}).get("final_certification", {}).get("certification_level")
            durability = genome_data.get("dimension_4_weaponizable", {}).get("vulnerability_map", {}).get("overall_durability_score")
        except Exception:
            pass

        if tid:
            save_genome(
                tid=tid,
                genome_json=genome_data,
                model=APIConfig.model(),
                schema_version="3.1.0",
                doc_id=doc_id,
                cert_level=cert_level,
                durability=durability,
            )
            try:
                from auto_tagger import tag_genome as _tag
                _tag(tid, genome_data)
            except Exception as tag_err:
                logging.getLogger(__name__).warning(f"Auto-tag failed for TID {tid}: {tag_err}")

        return jsonify({
            "genome": genome_data,
            "cached": False,
            "tid": tid,
            "model": APIConfig.model(),
            "input_tokens": message.usage.input_tokens if hasattr(message, 'usage') else None,
            "output_tokens": message.usage.output_tokens if hasattr(message, 'usage') else None,
        })

    except anthropic.APITimeoutError:
        return jsonify({"error": "Extraction timed out. The judgment may be too long. Try a shorter text."}), 504
    except anthropic.RateLimitError:
        return jsonify({"error": "Rate limited by Claude API. Please wait a moment and try again."}), 429
    except anthropic.BadRequestError as e:
        return jsonify({"error": f"Request rejected by Claude API (text may be too long): {str(e)}"}), 400
    except anthropic.APIError as e:
        return jsonify({"error": f"Claude API error: {str(e)}"}), 502
    except Exception as e:
        app.logger.error(f"Genome extraction failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/genome/<int:tid_val>")
def api_genome_get(tid_val):
    try:
        cached = get_cached_genome(tid_val)
        if not cached:
            return jsonify({"error": "No genome found for this judgment"}), 404
        genome_data = cached["genome_json"]
        if isinstance(genome_data, str):
            genome_data = json.loads(genome_data)
        return jsonify({
            "genome": genome_data,
            "tid": tid_val,
            "extraction_date": cached["extraction_date"].isoformat() if cached["extraction_date"] else "",
            "certification_level": cached["certification_level"],
            "overall_durability_score": cached["overall_durability_score"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/genome/list")
def api_genome_list():
    try:
        genomes = get_all_genomes()
        result = []
        for g in genomes:
            result.append({
                "id": g["id"],
                "tid": g["tid"],
                "title": g["title"] or "Untitled",
                "schema_version": g["schema_version"],
                "extraction_model": g["extraction_model"],
                "extraction_date": g["extraction_date"].isoformat() if g["extraction_date"] else "",
                "certification_level": g["certification_level"],
                "overall_durability_score": g["overall_durability_score"],
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/genome/validate", methods=["POST"])
def api_genome_validate():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body is required"}), 400
    genome_json = body.get("genome_json")
    if not genome_json:
        return jsonify({"error": "genome_json is required"}), 400
    if isinstance(genome_json, str):
        try:
            genome_json = json.loads(genome_json)
        except json.JSONDecodeError as e:
            return jsonify({"valid": False, "errors": [f"Invalid JSON: {str(e)}"]}), 200
    errors = _validate_genome_structure(genome_json)
    return jsonify({"valid": len(errors) == 0, "errors": errors})


@app.route("/api/genome/import", methods=["POST"])
def api_genome_import():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body is required"}), 400
    genome_json = body.get("genome_json")
    tid = body.get("tid")
    title = body.get("title", "")
    court = body.get("court", "")
    extraction_model = body.get("extraction_model", "manual-import")
    if not genome_json:
        return jsonify({"error": "genome_json is required"}), 400
    if isinstance(genome_json, str):
        try:
            genome_json = json.loads(genome_json)
        except json.JSONDecodeError as e:
            return jsonify({"error": f"Invalid JSON: {str(e)}"}), 400
    errors = _validate_genome_structure(genome_json)
    if errors:
        return jsonify({"error": "Genome validation failed", "validation_errors": errors}), 400
    overwrite = body.get("overwrite", False)
    if not tid:
        import random
        tid = random.randint(900000000, 999999999)
    try:
        tid = int(tid)
    except (ValueError, TypeError):
        return jsonify({"error": "tid must be a number"}), 400
    existing = get_cached_genome(tid)
    if existing and not overwrite:
        return jsonify({
            "error": "exists",
            "message": f"A genome already exists for TID {tid}. Set overwrite=true to replace it.",
            "existing_title": existing.get("genome_json", {}).get("extraction_metadata", {}).get("judgment_citation", str(tid)) if isinstance(existing.get("genome_json"), dict) else str(tid)
        }), 409
    doctype = body.get("doctype", "")
    if not title:
        meta = genome_json.get("extraction_metadata", {})
        title = meta.get("judgment_citation", "") or f"Imported Genome (TID {tid})"
    ensure_judgment_exists(tid, title, court or None, doctype=doctype or None)
    schema_ver = genome_json.get("schema_version", "3.1.0")
    doc_id = genome_json.get("document_id")
    cert_level = None
    durability = None
    audit = genome_json.get("dimension_6_audit", {})
    if audit:
        cert = audit.get("final_certification", {})
        cert_level = cert.get("certification_level")
        durability = cert.get("overall_durability_score")
        if durability is not None:
            try:
                durability = int(durability)
            except (ValueError, TypeError):
                durability = None
    try:
        saved = save_genome(tid, genome_json, model=extraction_model,
                            schema_version=schema_ver, doc_id=doc_id,
                            cert_level=cert_level, durability=durability)
        try:
            from auto_tagger import tag_genome as _tag
            _tag(tid, genome_json)
        except Exception as tag_err:
            logging.getLogger(__name__).warning(f"Auto-tag failed for TID {tid}: {tag_err}")
        return jsonify({
            "success": True,
            "tid": tid,
            "title": title,
            "id": saved["id"] if saved else None,
            "message": f"Genome saved for TID {tid}"
        })
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 500


@app.route("/api/genome/database")
def api_genome_database():
    query = request.args.get("q", "").strip()
    try:
        if query:
            genomes = search_genomes(query)
        else:
            genomes = get_all_genomes_rich()
        result = []
        for g in genomes:
            genome_data = g.get("genome_json", {})
            if isinstance(genome_data, str):
                try:
                    genome_data = json.loads(genome_data)
                except Exception:
                    genome_data = {}
            meta = genome_data.get("extraction_metadata", {})
            d1 = genome_data.get("dimension_1_visible", {})
            d5 = genome_data.get("dimension_5_synthesis", {})
            d4 = genome_data.get("dimension_4_weaponizable", {})
            case_id = d1.get("case_identity", {})
            cheat = d5.get("practitioners_cheat_sheet", {})
            provisions = d1.get("provisions_engaged", [])
            prov_list = []
            if isinstance(provisions, list):
                for p in provisions[:8]:
                    if isinstance(p, dict):
                        label = p.get("provision") or p.get("provision_id") or p.get("parent_statute") or ""
                        if not label and "parent_statute" in p:
                            label = p["parent_statute"]
                        if label:
                            prov_list.append(str(label))
                    elif isinstance(p, str) and len(p) < 100:
                        prov_list.append(p)
            ratio = d1.get("ratio_decidendi", {})
            core_ratio = ""
            if isinstance(ratio, dict):
                core_ratio = ratio.get("core_ratio", "") or ratio.get("holding", "")
            elif isinstance(ratio, list) and ratio:
                first = ratio[0]
                if isinstance(first, dict):
                    core_ratio = first.get("core_ratio", "") or first.get("proposition", "") or first.get("holding", "") or first.get("the_holding", "") or first.get("ratio_text", "")
                elif isinstance(first, str):
                    core_ratio = first
            elif isinstance(ratio, str):
                core_ratio = ratio
            result.append({
                "id": g["id"],
                "tid": g["tid"],
                "title": g.get("title") or meta.get("judgment_citation", f"TID {g['tid']}"),
                "court": g.get("court_source") or case_id.get("court", ""),
                "bench": case_id.get("bench", ""),
                "decided_date": case_id.get("decided_date", ""),
                "publish_date": str(g.get("publish_date", "")) if g.get("publish_date") else "",
                "num_cited_by": g.get("num_cited_by", 0) or 0,
                "schema_version": g["schema_version"],
                "extraction_model": g["extraction_model"],
                "extraction_date": g["extraction_date"].isoformat() if g.get("extraction_date") else "",
                "certification_level": g.get("certification_level"),
                "overall_durability_score": g.get("overall_durability_score"),
                "citation": meta.get("judgment_citation", ""),
                "provisions": prov_list,
                "core_ratio": core_ratio[:300] if core_ratio else "",
                "cite_when": cheat.get("cite_when", ""),
                "do_not_cite_when": cheat.get("do_not_cite_when", ""),
                "killer_paragraph": cheat.get("killer_paragraph", ""),
                "vulnerability_count": len(d4.get("vulnerability_map", [])) if isinstance(d4.get("vulnerability_map"), list) else 0,
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _validate_genome_structure(genome):
    errors = []
    required_top = [
        "document_id", "schema_version", "extraction_metadata",
        "dimension_1_visible", "dimension_2_structural",
        "dimension_3_invisible", "dimension_4_weaponizable",
        "dimension_5_synthesis", "dimension_6_audit"
    ]
    for key in required_top:
        if key not in genome:
            errors.append(f"Missing required top-level key: {key}")
    if errors:
        return errors
    meta = genome.get("extraction_metadata", {})
    if not isinstance(meta, dict):
        errors.append("extraction_metadata must be an object")
    else:
        for mk in ["extraction_date", "judgment_citation"]:
            if mk not in meta:
                errors.append(f"extraction_metadata missing: {mk}")
    d1 = genome.get("dimension_1_visible", {})
    if not isinstance(d1, dict):
        errors.append("dimension_1_visible must be an object")
    else:
        d1_keys = ["case_identity", "story", "ratio_decidendi", "operative_order", "provisions_engaged"]
        for dk in d1_keys:
            if dk not in d1:
                errors.append(f"dimension_1_visible missing: {dk}")
    d2 = genome.get("dimension_2_structural", {})
    if not isinstance(d2, dict):
        errors.append("dimension_2_structural must be an object")
    else:
        for dk in ["syllogisms", "interpretive_method"]:
            if dk not in d2:
                errors.append(f"dimension_2_structural missing: {dk}")
    d3 = genome.get("dimension_3_invisible", {})
    if not isinstance(d3, dict):
        errors.append("dimension_3_invisible must be an object")
    d4 = genome.get("dimension_4_weaponizable", {})
    if not isinstance(d4, dict):
        errors.append("dimension_4_weaponizable must be an object")
    else:
        for dk in ["sword_uses", "shield_uses", "vulnerability_map"]:
            if dk not in d4:
                errors.append(f"dimension_4_weaponizable missing: {dk}")
    d5 = genome.get("dimension_5_synthesis", {})
    if not isinstance(d5, dict):
        errors.append("dimension_5_synthesis must be an object")
    d6 = genome.get("dimension_6_audit", {})
    if not isinstance(d6, dict):
        errors.append("dimension_6_audit must be an object")
    return errors


@app.route("/api/questions/extract", methods=["POST"])
def api_questions_extract():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body is required"}), 400

    pleading_text = body.get("pleading_text", "").strip()
    pleading_type = body.get("pleading_type", "OTHER")
    citation = body.get("citation", "")

    if not pleading_text:
        return jsonify({"error": "Pleading text is required"}), 400

    if len(pleading_text) < 200:
        return jsonify({"error": "Pleading text too short. Minimum 200 characters required."}), 400

    if not APIConfig.is_configured():
        return jsonify({"error": "ANTHROPIC_API_KEY is not configured"}), 503

    text_hash = hashlib.sha256(pleading_text.encode("utf-8")).hexdigest()[:32]

    try:
        cached = get_question_extraction(text_hash)
        if cached:
            q_data = cached["questions_json"]
            if isinstance(q_data, str):
                q_data = json.loads(q_data)
            return jsonify({
                "questions": q_data,
                "cached": True,
                "question_count": cached["question_count"],
                "extracted_at": cached["extracted_at"].isoformat() if cached["extracted_at"] else "",
            })

        system_prompt = build_question_extractor_prompt()
        schema_summary = get_question_schema_summary()

        user_message = f"## OUTPUT SCHEMA\n{schema_summary}\n\n## PLEADING TYPE: {pleading_type}\n## CITATION: {citation}\n\n## PLEADING TEXT\n\n{pleading_text}"

        client = anthropic.Anthropic(api_key=APIConfig.api_key())
        message = client.messages.create(
            model=APIConfig.model(),
            max_tokens=APIConfig.max_tokens(),
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            timeout=APIConfig.timeout(),
        )

        response_text = message.content[0].text
        cleaned = strip_markdown_fences(response_text)

        try:
            questions_data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            app.logger.error(f"Questions JSON parse failed: {e}. First 500 chars: {cleaned[:500]}")
            return jsonify({"error": "Failed to parse question extraction output as JSON."}), 422

        total_q = 0
        try:
            total_q = questions_data.get("extraction_summary", {}).get("total_questions", 0)
        except Exception:
            pass

        save_question_extraction(
            text_hash=text_hash,
            pleading_type=pleading_type,
            citation=citation,
            questions_json=questions_data,
            question_count=total_q,
            model=APIConfig.model(),
        )

        return jsonify({
            "questions": questions_data,
            "cached": False,
            "question_count": total_q,
            "model": APIConfig.model(),
            "input_tokens": message.usage.input_tokens if hasattr(message, 'usage') else None,
            "output_tokens": message.usage.output_tokens if hasattr(message, 'usage') else None,
        })

    except anthropic.APITimeoutError:
        return jsonify({"error": "Extraction timed out. The pleading may be too long."}), 504
    except anthropic.RateLimitError:
        return jsonify({"error": "Rate limited by Claude API. Please wait and try again."}), 429
    except anthropic.BadRequestError as e:
        return jsonify({"error": f"Request rejected by Claude API (text may be too long): {str(e)}"}), 400
    except anthropic.APIError as e:
        return jsonify({"error": f"Claude API error: {str(e)}"}), 502
    except Exception as e:
        app.logger.error(f"Question extraction failed: {e}")
        return jsonify({"error": str(e)}), 500


VALID_PLEADING_TYPES = {
    "WRIT_PETITION", "BAIL_APPLICATION", "ANTICIPATORY_BAIL", "CIVIL_SUIT",
    "APPEAL_MEMO", "SPECIAL_LEAVE_PETITION", "CRIMINAL_COMPLAINT",
    "WRITTEN_STATEMENT", "COUNTER_AFFIDAVIT", "REVISION_PETITION",
    "REVIEW_PETITION", "CURATIVE_PETITION", "APPLICATION_UNDER_SPECIFIC_STATUTE",
    "ARBITRATION_PETITION", "COMPANY_PETITION", "EXECUTION_APPLICATION",
    "DISCHARGE_APPLICATION", "QUASHING_PETITION", "TRANSFER_PETITION", "OTHER"
}

PIPELINE_API_KEY = os.environ.get("PIPELINE_API_KEY", "")


def _check_pipeline_auth():
    if not PIPELINE_API_KEY:
        return True
    provided = request.headers.get("X-API-Key", "")
    return provided == PIPELINE_API_KEY


@app.route("/api/pipeline/submit", methods=["POST"])
def api_pipeline_submit():
    if not _check_pipeline_auth():
        return jsonify({"error": "Invalid API key"}), 401

    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body is required"}), 400

    pleading_text = body.get("pleading_text", "").strip()
    if not pleading_text or len(pleading_text) < 200:
        return jsonify({"error": "pleading_text is required (minimum 200 characters)"}), 400

    pleading_type = body.get("pleading_type", "OTHER")
    if pleading_type not in VALID_PLEADING_TYPES:
        pleading_type = "OTHER"

    if not APIConfig.is_configured():
        return jsonify({"error": "ANTHROPIC_API_KEY is not configured on server"}), 503

    try:
        job = create_research_job(
            pleading_text=pleading_text,
            pleading_type=pleading_type,
            citation=body.get("citation", ""),
            client_name=body.get("client_name", ""),
            client_side=body.get("client_side", ""),
            opposite_party=body.get("opposite_party", ""),
            court=body.get("court", ""),
            reliefs_sought=body.get("reliefs_sought"),
            callback_url=body.get("callback_url"),
            webhook_secret=body.get("webhook_secret"),
            priority=body.get("priority", "NORMAL"),
        )

        from pipeline import start_pipeline
        start_pipeline(job["id"])

        return jsonify({
            "job_id": str(job["id"]),
            "status": "RECEIVED",
            "message": "Pipeline started. Use /api/pipeline/status/<job_id> to track progress.",
            "estimated_time_minutes": "15-45",
        }), 202

    except Exception as e:
        app.logger.error(f"Pipeline submit failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/pipeline/status/<job_id>")
def api_pipeline_status(job_id):
    try:
        job = get_research_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        steps = [
            {"name": "EXTRACTING_QUESTIONS", "label": "Extract Questions", "completed_at": job.get("questions_completed_at")},
            {"name": "GENERATING_QUERIES", "label": "Generate Queries", "completed_at": job.get("queries_completed_at")},
            {"name": "SEARCHING", "label": "Search IK", "completed_at": job.get("searches_completed_at")},
            {"name": "FILTERING", "label": "Filter Relevance", "completed_at": job.get("filtering_completed_at")},
            {"name": "FETCHING_DOCS", "label": "Fetch Documents", "completed_at": job.get("fetching_completed_at")},
            {"name": "EXTRACTING_GENOMES", "label": "Extract Genomes", "completed_at": job.get("genomes_completed_at")},
            {"name": "SYNTHESIZING", "label": "Synthesize Memo", "completed_at": job.get("synthesis_completed_at")},
        ]

        for s in steps:
            if s["completed_at"]:
                s["completed_at"] = s["completed_at"].isoformat()
                s["status"] = "COMPLETED"
            elif job.get("current_step") == s["name"]:
                s["status"] = "IN_PROGRESS"
            else:
                s["status"] = "PENDING"

        cost_usd = job.get("cost_estimate_usd") or 0
        cost_breakdown = job.get("cost_breakdown_json")
        if isinstance(cost_breakdown, str):
            try:
                cost_breakdown = json.loads(cost_breakdown)
            except Exception:
                cost_breakdown = {}

        result = {
            "job_id": str(job["id"]),
            "status": job["status"],
            "current_step": job.get("current_step"),
            "steps": steps,
            "stats": {
                "total_questions": job.get("total_questions", 0),
                "total_queries": job.get("total_queries_generated", 0),
                "total_searches": job.get("total_searches_completed", 0),
                "total_results": job.get("total_results_found", 0),
                "relevant_judgments": job.get("total_relevant_judgments", 0),
                "genomes_extracted": job.get("total_genomes_extracted", 0),
            },
            "cost": {
                "total_usd": round(cost_usd, 4),
                "total_inr": round(cost_usd * 95, 2),
                "breakdown": cost_breakdown or {},
            },
            "citation": job.get("citation", ""),
            "pleading_type": job.get("pleading_type", ""),
            "created_at": job["created_at"].isoformat() if job.get("created_at") else "",
            "started_at": job["started_at"].isoformat() if job.get("started_at") else "",
            "completed_at": job["completed_at"].isoformat() if job.get("completed_at") else "",
            "error_message": job.get("error_message"),
        }
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pipeline/result/<job_id>")
def api_pipeline_result(job_id):
    try:
        job = get_research_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        if job["status"] != "COMPLETED":
            return jsonify({
                "error": f"Job not yet completed. Current status: {job['status']}",
                "status": job["status"],
                "current_step": job.get("current_step"),
            }), 202

        memo = job.get("research_memo")
        if isinstance(memo, str):
            memo = json.loads(memo)

        return jsonify({
            "job_id": str(job["id"]),
            "status": "COMPLETED",
            "research_memo": memo,
            "stats": {
                "total_questions": job.get("total_questions", 0),
                "queries_executed": job.get("total_queries_generated", 0),
                "judgments_found": job.get("total_results_found", 0),
                "relevant_judgments": job.get("total_relevant_judgments", 0),
                "genomes_extracted": job.get("total_genomes_extracted", 0),
            },
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pipeline/retry/<job_id>", methods=["POST"])
def api_pipeline_retry(job_id):
    if not _check_pipeline_auth():
        return jsonify({"error": "Invalid API key"}), 401

    try:
        from pipeline import resume_pipeline
        success, msg = resume_pipeline(job_id)
        if success:
            return jsonify({"job_id": job_id, "status": "RESUMED", "message": msg})
        return jsonify({"error": msg}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pipeline/list")
def api_pipeline_list():
    try:
        jobs = get_all_research_jobs()
        result = []
        for j in jobs:
            result.append({
                "job_id": str(j["id"]),
                "status": j["status"],
                "citation": j.get("citation", ""),
                "client_name": j.get("client_name", ""),
                "pleading_type": j.get("pleading_type", ""),
                "court": j.get("court", ""),
                "current_step": j.get("current_step"),
                "total_questions": j.get("total_questions", 0),
                "total_queries": j.get("total_queries_generated", 0),
                "total_searches": j.get("total_searches_completed", 0),
                "relevant_judgments": j.get("total_relevant_judgments", 0),
                "genomes_extracted": j.get("total_genomes_extracted", 0),
                "cost_usd": round(j.get("cost_estimate_usd") or 0, 4),
                "cost_inr": round((j.get("cost_estimate_usd") or 0) * 95, 2),
                "created_at": j["created_at"].isoformat() if j.get("created_at") else "",
                "started_at": j["started_at"].isoformat() if j.get("started_at") else "",
                "completed_at": j["completed_at"].isoformat() if j.get("completed_at") else "",
                "error_message": j.get("error_message"),
                "questions_completed_at": j["questions_completed_at"].isoformat() if j.get("questions_completed_at") else None,
                "queries_completed_at": j["queries_completed_at"].isoformat() if j.get("queries_completed_at") else None,
                "searches_completed_at": j["searches_completed_at"].isoformat() if j.get("searches_completed_at") else None,
                "filtering_completed_at": j["filtering_completed_at"].isoformat() if j.get("filtering_completed_at") else None,
                "fetching_completed_at": j["fetching_completed_at"].isoformat() if j.get("fetching_completed_at") else None,
                "genomes_completed_at": j["genomes_completed_at"].isoformat() if j.get("genomes_completed_at") else None,
                "synthesis_completed_at": j["synthesis_completed_at"].isoformat() if j.get("synthesis_completed_at") else None,
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/taxonomy/categories")
def api_taxonomy_categories():
    try:
        cats = get_all_taxonomy_categories()
        result = []
        for c in cats:
            result.append({
                "id": c["id"],
                "name": c["name"],
                "parent_statute": c.get("parent_statute", ""),
                "description": c.get("description", ""),
                "genome_count": c.get("genome_count", 0),
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/taxonomy/categories/<cat_id>/genomes")
def api_taxonomy_category_genomes(cat_id):
    try:
        genomes = get_genomes_for_category(cat_id)
        result = []
        for g in genomes:
            result.append({
                "tid": g["tid"],
                "title": g.get("title", ""),
                "court_source": g.get("court_source", ""),
                "publish_date": g["publish_date"].isoformat() if g.get("publish_date") else "",
                "num_cited_by": g.get("num_cited_by", 0),
                "durability_score": g.get("overall_durability_score"),
                "extraction_model": g.get("extraction_model", ""),
                "certification_level": g.get("certification_level", ""),
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/taxonomy/topics")
def api_taxonomy_topics():
    try:
        category_id = request.args.get("category_id")
        topics = get_taxonomy_topics(category_id)
        result = []
        for t in topics:
            result.append({
                "id": t["id"],
                "category_id": t.get("category_id", ""),
                "name": t["name"],
                "description": t.get("description", ""),
                "keywords": t.get("keywords", []),
                "genome_count": t.get("genome_count", 0),
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/taxonomy/topics/<topic_id>/genomes")
def api_taxonomy_topic_genomes(topic_id):
    try:
        genomes = get_genomes_for_topic(topic_id)
        result = []
        for g in genomes:
            result.append({
                "tid": g["tid"],
                "title": g.get("title", ""),
                "court_source": g.get("court_source", ""),
                "publish_date": g["publish_date"].isoformat() if g.get("publish_date") else "",
                "num_cited_by": g.get("num_cited_by", 0),
                "durability_score": g.get("overall_durability_score"),
                "extraction_model": g.get("extraction_model", ""),
                "certification_level": g.get("certification_level", ""),
                "confidence": g.get("confidence", 1.0),
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/taxonomy/provisions")
def api_taxonomy_provisions():
    try:
        provs = get_all_provisions()
        result = []
        for p in provs:
            result.append({
                "id": p["id"],
                "canonical_name": p["canonical_name"],
                "parent_statute": p.get("parent_statute", ""),
                "aliases": p.get("aliases", []),
                "category_id": p.get("category_id", ""),
                "category_name": p.get("category_name", ""),
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/taxonomy/search")
def api_taxonomy_search():
    try:
        q = request.args.get("q", "").strip()
        if not q or len(q) < 2:
            return jsonify([])
        results = search_taxonomy(q)
        return jsonify([dict(r) for r in results])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/taxonomy/genome/<int:tid>/tags")
def api_genome_tags(tid):
    try:
        tags = get_genome_tags(tid)
        return jsonify(tags)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/taxonomy/stats")
def api_taxonomy_stats():
    try:
        stats = get_taxonomy_stats()
        return jsonify(dict(stats))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


_retag_last_run = [0]

@app.route("/api/taxonomy/retag", methods=["POST"])
def api_taxonomy_retag():
    import time as _time
    now = _time.time()
    if now - _retag_last_run[0] < 30:
        remaining = int(30 - (now - _retag_last_run[0]))
        return jsonify({"error": f"Rate limited. Try again in {remaining} seconds."}), 429
    try:
        _retag_last_run[0] = now
        from auto_tagger import tag_all_genomes
        result = tag_all_genomes()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/taxonomy/heatmap")
def api_taxonomy_heatmap():
    try:
        data = get_coverage_heatmap()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/taxonomy/topics/<topic_id>/synthesize", methods=["POST"])
def api_topic_synthesize(topic_id):
    try:
        from topic_synthesis import synthesize_topic
        data = request.get_json(silent=True) or {}
        force = data.get("force", False)
        synthesis, usage = synthesize_topic(topic_id, force=force)
        return jsonify({"synthesis": synthesis, "usage": usage})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/taxonomy/topics/<topic_id>/synthesis")
def api_topic_synthesis_cached(topic_id):
    try:
        cached = get_topic_synthesis(topic_id)
        if not cached:
            return jsonify({"exists": False})
        return jsonify({
            "exists": True,
            "synthesis": cached["synthesis_json"],
            "topic_name": cached.get("topic_name", ""),
            "genome_count": cached.get("genome_count", 0),
            "created_at": cached["created_at"].isoformat() if cached.get("created_at") else None,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/taxonomy/compare", methods=["POST"])
def api_taxonomy_compare():
    try:
        data = request.get_json()
        tids = data.get("tids", [])
        if not tids or len(tids) < 2 or len(tids) > 3:
            return jsonify({"error": "Provide 2-3 TIDs for comparison"}), 400

        genomes = get_genomes_for_comparison(tids)
        if len(genomes) < 2:
            return jsonify({"error": "Not all TIDs have genomes"}), 404

        result = []
        for g in genomes:
            genome_json = g["genome_json"]
            d1 = genome_json.get("dimension_1_visible", {})
            d4 = genome_json.get("dimension_4_weaponizable", {})
            d5 = genome_json.get("dimension_5_synthesis", {})

            result.append({
                "tid": g["tid"],
                "title": g.get("title", ""),
                "court_source": g.get("court_source", ""),
                "publish_date": g["publish_date"].isoformat() if g.get("publish_date") else "",
                "durability_score": g.get("overall_durability_score"),
                "case_identity": d1.get("case_identity", {}),
                "ratio_decidendi": d1.get("ratio_decidendi", []),
                "provisions_engaged": d1.get("provisions_engaged", []),
                "sword_uses": d4.get("sword_uses", []),
                "shield_uses": d4.get("shield_uses", []),
                "vulnerability_map": d4.get("vulnerability_map", {}),
                "cheat_sheet": d5.get("practitioners_cheat_sheet", {}),
                "genome_summary": d5.get("genome_summary", ""),
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/taxonomy/topics/<topic_id>/scan-conflicts", methods=["POST"])
def api_topic_scan_conflicts(topic_id):
    try:
        from conflict_radar import scan_conflicts
        scan, usage = scan_conflicts(topic_id)
        return jsonify({"scan": scan, "usage": usage})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/taxonomy/topics/<topic_id>/conflicts")
def api_topic_conflicts_cached(topic_id):
    try:
        cached = get_conflict_scan(topic_id)
        if not cached:
            return jsonify({"exists": False})
        return jsonify({
            "exists": True,
            "scan": cached["scan_json"],
            "genome_count": cached.get("genome_count", 0),
            "created_at": cached["created_at"].isoformat() if cached.get("created_at") else None,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/district/courts")
def api_district_courts():
    try:
        city = request.args.get("city")
        courts = get_district_courts(city)
        return jsonify([dict(c) for c in courts])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/district/courts/<int:court_id>/judges")
def api_district_court_judges(court_id):
    try:
        judges = get_district_judges(court_id)
        result = []
        for j in judges:
            result.append({
                "id": j["id"], "name": j["name"],
                "designation": j.get("designation", ""),
                "court_name": j.get("court_name", ""),
                "specializations": j.get("specializations", []),
                "active": j.get("active", True),
                "order_count": j.get("order_count", 0),
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/district/judges/<int:judge_id>")
def api_district_judge_detail(judge_id):
    try:
        judge = get_district_judge(judge_id)
        if not judge:
            return jsonify({"error": "Judge not found"}), 404
        return jsonify(dict(judge))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/district/judges/<int:judge_id>/orders")
def api_district_judge_orders(judge_id):
    try:
        page = request.args.get("page", 1, type=int)
        orders = get_district_orders(judge_id, page=page)
        result = []
        total = 0
        for o in orders:
            total = o.get("total", 0)
            row = dict(o)
            row.pop("total", None)
            if row.get("order_date"):
                row["order_date"] = row["order_date"].isoformat()
            if row.get("created_at"):
                row["created_at"] = row["created_at"].isoformat()
            result.append(row)
        return jsonify({"orders": result, "total": total, "page": page})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/district/judges", methods=["POST"])
def api_add_district_judge():
    try:
        data = request.get_json()
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Name is required"}), 400
        court_id = data.get("court_id")
        if not court_id:
            return jsonify({"error": "Court ID is required"}), 400
        judge_id = add_district_judge(
            name=name,
            designation=data.get("designation", ""),
            court_id=int(court_id),
            specializations=data.get("specializations", []),
        )
        return jsonify({"id": judge_id, "name": name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/district/orders", methods=["POST"])
def api_add_district_order():
    try:
        data = request.get_json()
        judge_id = data.get("judge_id")
        court_id = data.get("court_id")
        if not judge_id or not court_id:
            return jsonify({"error": "judge_id and court_id are required"}), 400
        order_id = add_district_order(
            judge_id=int(judge_id),
            court_id=int(court_id),
            order_date=data.get("order_date"),
            case_type=data.get("case_type", ""),
            case_number=data.get("case_number", ""),
            petitioner=data.get("petitioner", ""),
            respondent=data.get("respondent", ""),
            order_text=data.get("order_text", ""),
            order_source_url=data.get("order_source_url"),
            tid=data.get("tid"),
        )
        return jsonify({"id": order_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/district/judges/<int:judge_id>/profile")
def api_judge_profile(judge_id):
    try:
        profile = get_judge_profile(judge_id)
        if not profile:
            return jsonify({"exists": False})
        return jsonify({
            "exists": True,
            "profile": profile["profile_json"],
            "total_orders_analyzed": profile.get("total_orders_analyzed", 0),
            "last_updated": profile["last_updated"].isoformat() if profile.get("last_updated") else None,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/district/judges/<int:judge_id>/analyze", methods=["POST"])
def api_analyze_judge(judge_id):
    return jsonify({"error": "Judge analysis is coming soon. Import more orders first."}), 501


@app.route("/api/district/fetched-judgments")
def api_district_fetched_judgments():
    try:
        rows = get_fetched_dc_judgments(limit=50)
        result = []
        for r in rows:
            result.append({
                "tid": r["tid"],
                "title": r["title"],
                "court_source": r.get("court_source"),
                "publish_date": r.get("publish_date"),
                "html_length": r.get("html_length", 0),
                "has_genome": r.get("has_genome", False),
                "durability_score": r.get("overall_durability_score"),
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/expressway/research", methods=["POST"])
def api_expressway_research():
    if not _check_pipeline_auth():
        return jsonify({"error": "Invalid API key"}), 401
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body is required"}), 400
    pleading_text = body.get("pleading_text", "").strip()
    if not pleading_text or len(pleading_text) < 100:
        return jsonify({"error": "pleading_text is required (minimum 100 characters)"}), 400
    try:
        max_judgments = min(int(body.get("max_judgments", 15)), 25)
    except (ValueError, TypeError):
        max_judgments = 15
    callback_url = body.get("callback_url", "").strip()
    if callback_url:
        from urllib.parse import urlparse
        parsed = urlparse(callback_url)
        if parsed.scheme not in ("http", "https"):
            return jsonify({"error": "callback_url must use http or https"}), 400
        host = parsed.hostname or ""
        if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.startswith("10.") or host.startswith("192.168.") or host.startswith("172."):
            return jsonify({"error": "callback_url must not point to private/internal addresses"}), 400
    webhook_secret = body.get("webhook_secret", "")
    pleading_json = {
        "pleading_text": pleading_text,
        "pleading_type": body.get("pleading_type", ""),
        "court": body.get("court", ""),
        "client_name": body.get("client_name", ""),
        "reliefs_sought": body.get("reliefs_sought", ""),
    }
    if callback_url:
        import uuid
        from db import create_expressway_job, update_expressway_status, save_expressway_result
        from expressway import run_expressway, pleading_hash as _ph
        job_id = str(uuid.uuid4())[:12]
        create_expressway_job(job_id, _ph(pleading_text), callback_url)
        def _run_async():
            try:
                update_expressway_status(job_id, "SEARCHING")
                result = run_expressway(pleading_json, max_judgments=max_judgments)
                if result.get("success"):
                    save_expressway_result(
                        job_id, result,
                        int(result.get("execution_time_seconds", 0) * 1000),
                        result.get("token_usage", {}).get("total_input_tokens", 0),
                        result.get("token_usage", {}).get("total_output_tokens", 0),
                        result.get("token_usage", {}).get("total_cost_usd", 0),
                    )
                else:
                    update_expressway_status(job_id, "FAILED", error_message=result.get("error", "Unknown"))
                _deliver_expressway_webhook(job_id, callback_url, webhook_secret, result)
            except Exception as e:
                app.logger.error(f"Expressway async job {job_id} failed: {e}")
                update_expressway_status(job_id, "FAILED", error_message=str(e))
        import threading
        t = threading.Thread(target=_run_async, daemon=True)
        t.start()
        return jsonify({
            "job_id": job_id,
            "status": "PROCESSING",
            "message": "Expressway research started. Result will be delivered to callback_url.",
            "estimated_time_seconds": "25-45",
        }), 202
    else:
        from expressway import run_expressway
        try:
            result = run_expressway(pleading_json, max_judgments=max_judgments)
            return jsonify(result)
        except Exception as e:
            app.logger.error(f"Expressway sync failed: {e}")
            return jsonify({"error": str(e), "success": False}), 500


def _deliver_expressway_webhook(job_id, callback_url, webhook_secret, result):
    import hmac, hashlib
    event = "expressway.completed" if result.get("success") else "expressway.failed"
    try:
        payload = json.dumps({
            "job_id": job_id,
            "event": event,
            "result": result,
        })
        headers = {"Content-Type": "application/json"}
        if webhook_secret:
            sig = hmac.new(webhook_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
            headers["X-Hub-Signature-256"] = f"sha256={sig}"
        import requests as req_lib
        resp = req_lib.post(callback_url, data=payload, headers=headers, timeout=30)
        app.logger.info(f"Expressway webhook delivered for {job_id}: {resp.status_code}")
        from db import update_expressway_status
        update_expressway_status(job_id, callback_delivered=True)
    except Exception as e:
        app.logger.error(f"Expressway webhook delivery failed for {job_id}: {e}")


@app.route("/api/expressway/status/<job_id>")
def api_expressway_status(job_id):
    from db import get_expressway_job
    job = get_expressway_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "job_id": job["job_id"],
        "status": job["status"],
        "created_at": job["created_at"].isoformat() if job.get("created_at") else None,
        "completed_at": job["completed_at"].isoformat() if job.get("completed_at") else None,
        "execution_time_ms": job.get("execution_time_ms"),
    })


@app.route("/api/expressway/result/<job_id>")
def api_expressway_result(job_id):
    from db import get_expressway_job
    job = get_expressway_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] != "COMPLETED":
        return jsonify({"error": f"Job status is {job['status']}, not COMPLETED yet"}), 400
    return jsonify(job.get("result_json", {}))


@app.route("/api/genome-research", methods=["POST"])
def api_genome_research():
    body = request.get_json(silent=True)
    if not body or not body.get("question"):
        return jsonify({"error": "Missing 'question' field"}), 400
    question = body["question"].strip()
    if len(question) < 10:
        return jsonify({"error": "Question too short (minimum 10 characters)"}), 400
    max_genomes = min(int(body.get("max_genomes", 15)), 30)
    try:
        from genome_research import run_genome_research
        result = run_genome_research(question, max_genomes=max_genomes)
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"[genome-research] API error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/genome-research/discover")
def api_genome_research_discover():
    question = request.args.get("q", "").strip()
    if not question or len(question) < 10:
        return jsonify({"error": "Missing or too short 'q' parameter"}), 400
    try:
        from genome_research import expand_query, discover_relevant_genomes, filter_relevant
        expanded = expand_query(question)
        discovery = discover_relevant_genomes(expanded)
        filtered = filter_relevant(question, discovery["candidates"])
        relevant = filtered["relevant"]
        expanded_clean = {k: v for k, v in expanded.items() if k not in ("usage", "timing_ms")}
        return jsonify({
            "success": True,
            "expanded_query": expanded_clean,
            "discovery": {
                "total_genomes_searched": discovery["total_searched"],
                "candidates_found": len(discovery["candidates"]),
                "relevant_found": len(relevant),
            },
            "relevant_judgments": [
                {
                    "tid": g["tid"],
                    "title": g["title"],
                    "court": g["court"],
                    "date": g["date"],
                    "cited_by": g.get("cited_by", 0),
                    "durability": g.get("durability", 0),
                    "relevance_score": g.get("relevance_score", 0),
                    "relevance_reason": g.get("relevance_reason", ""),
                    "signals": g.get("signals", []),
                }
                for g in relevant
            ],
        })
    except Exception as e:
        app.logger.error(f"[genome-research] Discover error: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


try:
    init_db()
    seed_default_templates()
except Exception as e:
    print(f"Warning: Could not initialize database: {e}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
