"""
Pipeline Orchestrator — autonomous legal research pipeline.
Pleading → Questions → Queries → Search → Filter → Fetch → Genome → Synthesis
"""
import hashlib
import json
import logging
import os
import threading
import time
import traceback
from datetime import datetime
from cost_tracker import PipelineCostTracker

logger = logging.getLogger(__name__)

PIPELINE_STEPS = [
    "EXTRACTING_QUESTIONS",
    "GENERATING_QUERIES",
    "SEARCHING",
    "FILTERING",
    "FETCHING_DOCS",
    "EXTRACTING_GENOMES",
    "SYNTHESIZING",
    "COMPLETED",
]

MAX_QUESTIONS_TO_PROCESS = 50
MAX_RELEVANT_JUDGMENTS = 35
RELEVANCE_THRESHOLD = 6.0
IK_SEARCH_DELAY = 2.0
MAX_COST_USD = 75.0

_active_jobs = {}


def _check_cost_limit(job_id, cost_tracker):
    if cost_tracker.get_total_usd() >= MAX_COST_USD:
        from db import update_research_job
        _save_costs(job_id, cost_tracker)
        update_research_job(job_id, status="FAILED", failed_at=datetime.now(),
                            error_message=f"Cost limit exceeded: ${cost_tracker.get_total_usd():.2f} >= ${MAX_COST_USD:.2f} (₹{cost_tracker.get_total_inr():.2f}). Resume with retry after review.")
        raise RuntimeError(f"Cost limit ${MAX_COST_USD} exceeded")


def start_pipeline(job_id):
    t = threading.Thread(target=_run_pipeline, args=(str(job_id),), daemon=True)
    t.name = f"pipeline-{job_id}"
    _active_jobs[str(job_id)] = t
    t.start()
    return t


def _run_pipeline(job_id):
    from db import get_research_job, update_research_job
    cost_tracker = PipelineCostTracker()
    try:
        job = get_research_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        update_research_job(job_id, status="EXTRACTING_QUESTIONS",
                            started_at=datetime.now(), current_step="EXTRACTING_QUESTIONS")

        _step_extract_questions(job_id, job, cost_tracker)

        job = get_research_job(job_id)
        if job["status"] == "FAILED":
            return

        _step_generate_queries(job_id, job, cost_tracker)

        job = get_research_job(job_id)
        if job["status"] == "FAILED":
            return

        _step_search(job_id, job, cost_tracker)

        job = get_research_job(job_id)
        if job["status"] == "FAILED":
            return

        _step_filter(job_id, job, cost_tracker)

        job = get_research_job(job_id)
        if job["status"] == "FAILED":
            return

        _step_fetch_docs(job_id, job, cost_tracker)

        job = get_research_job(job_id)
        if job["status"] == "FAILED":
            return

        _step_extract_genomes(job_id, job, cost_tracker)

        job = get_research_job(job_id)
        if job["status"] == "FAILED":
            return

        _step_synthesize(job_id, job, cost_tracker)

        job = get_research_job(job_id)
        if job["status"] == "FAILED":
            return

        _save_costs(job_id, cost_tracker)
        update_research_job(job_id, status="COMPLETED",
                            completed_at=datetime.now(), current_step="COMPLETED")
        logger.info(f"Pipeline {job_id} COMPLETED — Total cost: {cost_tracker.get_total_usd():.4f} USD (₹{cost_tracker.get_total_inr():.2f})")

        _deliver_result(job_id)

    except Exception as e:
        logger.error(f"Pipeline {job_id} crashed: {e}\n{traceback.format_exc()}")
        try:
            update_research_job(job_id, status="FAILED",
                                failed_at=datetime.now(),
                                error_message=str(e)[:1000])
        except Exception:
            pass
    finally:
        _active_jobs.pop(str(job_id), None)


def _save_costs(job_id, cost_tracker):
    from db import update_research_job
    update_research_job(job_id,
                        cost_estimate_usd=cost_tracker.get_total_usd(),
                        cost_breakdown_json=cost_tracker.get_breakdown())


def _repair_truncated_json(text):
    close_positions = []
    in_string = False
    escape_next = False
    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('}', ']'):
            close_positions.append(i)

    for pos in reversed(close_positions[-500:]):
        candidate = text[:pos + 1]
        stack = []
        s_in_str = False
        s_esc = False
        for ch in candidate:
            if s_esc:
                s_esc = False
                continue
            if ch == '\\' and s_in_str:
                s_esc = True
                continue
            if ch == '"':
                s_in_str = not s_in_str
                continue
            if s_in_str:
                continue
            if ch in ('{', '['):
                stack.append(ch)
            elif ch == '}' and stack and stack[-1] == '{':
                stack.pop()
            elif ch == ']' and stack and stack[-1] == '[':
                stack.pop()

        suffix = "".join(']' if o == '[' else '}' for o in reversed(stack))
        try:
            result = json.loads(candidate + suffix)
            if isinstance(result, dict):
                return candidate + suffix
        except json.JSONDecodeError:
            continue

    raise json.JSONDecodeError("Could not repair truncated JSON", text, 0)


def _step_extract_questions(job_id, job, cost_tracker):
    from db import update_research_job, get_question_extraction, save_question_extraction
    from genome_config import (
        APIConfig, build_question_extractor_prompt, get_question_schema_summary,
        strip_markdown_fences
    )
    import anthropic

    logger.info(f"[{job_id}] Step 1: Extracting questions")

    text_hash = hashlib.sha256(job["pleading_text"].encode("utf-8")).hexdigest()[:32]

    cached = get_question_extraction(text_hash)
    if cached:
        q_data = cached["questions_json"]
        if isinstance(q_data, str):
            q_data = json.loads(q_data)

        total_q = cached["question_count"] or 0
        update_research_job(job_id,
                            question_extraction_id=cached["id"],
                            total_questions=total_q,
                            questions_completed_at=datetime.now(),
                            current_step="GENERATING_QUERIES",
                            status="GENERATING_QUERIES")
        logger.info(f"[{job_id}] Questions cached: {total_q}")
        return

    if not APIConfig.is_configured():
        update_research_job(job_id, status="FAILED", failed_at=datetime.now(),
                            error_message="ANTHROPIC_API_KEY not configured")
        return

    system_prompt = build_question_extractor_prompt()
    schema_summary = get_question_schema_summary()
    pleading_type = job["pleading_type"] or "OTHER"
    citation = job["citation"] or ""

    user_message = (
        f"## OUTPUT SCHEMA\n{schema_summary}\n\n"
        f"## IMPORTANT CONSTRAINTS\n"
        f"- Limit to the TOP 40 most important questions across all categories.\n"
        f"- Keep why_this_matters and research_direction fields to 1-2 sentences each.\n"
        f"- Only include categories that have relevant questions (skip empty categories).\n"
        f"- Prioritize CRITICAL and HIGH importance questions.\n\n"
        f"## PLEADING TYPE: {pleading_type}\n## CITATION: {citation}\n\n"
        f"## PLEADING TEXT\n\n{job['pleading_text']}"
    )

    try:
        client = anthropic.Anthropic(api_key=APIConfig.api_key())
        message = client.messages.create(
            model=APIConfig.model(),
            max_tokens=APIConfig.max_tokens(),
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            timeout=600,
        )

        if hasattr(message, "usage"):
            cost_tracker.add_claude_cost("question_extraction", APIConfig.model(),
                                          message.usage.input_tokens, message.usage.output_tokens)
            _save_costs(job_id, cost_tracker)

        response_text = message.content[0].text
        stop_reason = getattr(message, "stop_reason", None)
        was_truncated = (stop_reason == "max_tokens")
        if was_truncated:
            logger.warning(f"[{job_id}] Question extraction output was truncated (max_tokens hit). Attempting JSON repair.")

        cleaned = strip_markdown_fences(response_text)

        try:
            questions_data = json.loads(cleaned)
        except json.JSONDecodeError:
            if was_truncated:
                logger.info(f"[{job_id}] Repairing truncated JSON ({len(cleaned)} chars)")
                repaired = _repair_truncated_json(cleaned)
                questions_data = json.loads(repaired)
                logger.info(f"[{job_id}] JSON repair successful")
            else:
                raise

        total_q = 0
        try:
            total_q = questions_data.get("extraction_summary", {}).get("total_questions", 0)
        except Exception:
            pass
        if total_q == 0:
            for cat_key, cat_val in questions_data.get("question_categories", {}).items():
                if isinstance(cat_val, dict):
                    total_q += len(cat_val.get("questions", []))

        saved = save_question_extraction(text_hash, pleading_type, citation,
                                          questions_data, total_q, APIConfig.model())

        update_research_job(job_id,
                            question_extraction_id=saved["id"] if saved else None,
                            total_questions=total_q,
                            questions_completed_at=datetime.now(),
                            current_step="GENERATING_QUERIES",
                            status="GENERATING_QUERIES")
        logger.info(f"[{job_id}] Extracted {total_q} questions")

    except Exception as e:
        _save_costs(job_id, cost_tracker)
        update_research_job(job_id, status="FAILED", failed_at=datetime.now(),
                            error_message=f"Question extraction failed: {str(e)[:500]}")
        raise


def _step_generate_queries(job_id, job, cost_tracker):
    from db import (update_research_job, get_question_extraction,
                    save_pipeline_query, get_pipeline_queries)
    from query_generator import generate_queries_batch, deduplicate_queries

    logger.info(f"[{job_id}] Step 2: Generating queries")

    existing_queries = get_pipeline_queries(job_id)
    if existing_queries:
        update_research_job(job_id,
                            total_queries_generated=len(existing_queries),
                            queries_completed_at=datetime.now(),
                            current_step="SEARCHING",
                            status="SEARCHING")
        return

    job = _reload_job(job_id)
    q_ext_id = job.get("question_extraction_id")
    if not q_ext_id:
        update_research_job(job_id, status="FAILED", failed_at=datetime.now(),
                            error_message="No question extraction found")
        return

    from db import get_db_connection
    import psycopg2.extras
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM question_extractions WHERE id = %s", (q_ext_id,))
            q_ext = cur.fetchone()
    finally:
        conn.close()

    if not q_ext:
        update_research_job(job_id, status="FAILED", failed_at=datetime.now(),
                            error_message="Question extraction record not found")
        return

    q_data = q_ext["questions_json"]
    if isinstance(q_data, str):
        q_data = json.loads(q_data)

    prioritized = _prioritize_questions(q_data)
    logger.info(f"[{job_id}] Prioritized {len(prioritized)} questions for query generation")

    case_context = {
        "court": job.get("court", ""),
        "pleading_type": job.get("pleading_type", ""),
        "client_side": job.get("client_side", ""),
        "reliefs_sought": job.get("reliefs_sought") or [],
    }
    if isinstance(case_context["reliefs_sought"], str):
        try:
            case_context["reliefs_sought"] = json.loads(case_context["reliefs_sought"])
        except Exception:
            case_context["reliefs_sought"] = []

    batch_size = 12
    all_generated = []
    for i in range(0, len(prioritized), batch_size):
        batch = prioritized[i:i + batch_size]
        batch_input = [
            {"question_id": q["id"], "text": q["text"], "category": q["category"]}
            for q in batch
        ]
        results, usage = generate_queries_batch(batch_input, case_context)

        if usage:
            cost_tracker.add_claude_cost("query_generation", usage.get("model", "claude-3-haiku-20240307"),
                                          usage.get("input_tokens", 0), usage.get("output_tokens", 0))

        for q in batch:
            q_queries = results.get(q["id"], {}).get("queries", [])
            for gq in q_queries:
                saved = save_pipeline_query(
                    job_id=job_id,
                    question_id=q["id"],
                    question_text=q["text"],
                    question_category=q["category"],
                    question_importance=q["importance"],
                    generated_ik_query=gq.get("ik_query", ""),
                    ik_doctype=gq.get("doctype", ""),
                    ik_sort=gq.get("sort", ""),
                )
                if saved:
                    all_generated.append(saved)

        time.sleep(0.5)

    _save_costs(job_id, cost_tracker)
    update_research_job(job_id,
                        total_queries_generated=len(all_generated),
                        queries_completed_at=datetime.now(),
                        current_step="SEARCHING",
                        status="SEARCHING")
    logger.info(f"[{job_id}] Generated {len(all_generated)} queries")


def _step_search(job_id, job, cost_tracker):
    from db import (update_research_job, get_pipeline_queries,
                    save_pipeline_result, update_pipeline_query,
                    save_judgment_metadata)

    logger.info(f"[{job_id}] Step 3: Executing searches")

    queries = get_pipeline_queries(job_id)
    pending = [q for q in queries if not q["search_completed"]]

    if not pending:
        total_results = _count_pipeline_results(job_id)
        update_research_job(job_id,
                            total_searches_completed=len(queries),
                            total_results_found=total_results,
                            searches_completed_at=datetime.now(),
                            current_step="FILTERING",
                            status="FILTERING")
        return

    import http.client
    import urllib.parse
    from app import API_HOST, get_api_token, parse_total_from_found, sanitize_html, parse_publish_date

    token = get_api_token()
    completed = len(queries) - len(pending)

    for pq in pending:
        ik_query = pq["generated_ik_query"]
        if not ik_query:
            update_pipeline_query(pq["id"], search_completed=True, results_count=0)
            completed += 1
            continue

        form_input = ik_query
        doctype = pq.get("ik_doctype", "")
        if doctype:
            form_input += f" doctypes: {doctype}"

        encoded = urllib.parse.quote_plus(form_input)
        url = f"/search/?formInput={encoded}&pagenum=0"

        try:
            headers = {"Authorization": f"Token {token}", "Accept": "application/json"}
            connection = http.client.HTTPSConnection(API_HOST, timeout=30)
            try:
                connection.request("POST", url, headers=headers)
                response = connection.getresponse()
                raw = response.read().decode("utf8")
                if response.status >= 400:
                    logger.warning(f"[{job_id}] Search failed for query '{ik_query}': HTTP {response.status}")
                    update_pipeline_query(pq["id"], search_completed=True, results_count=0)
                    completed += 1
                    time.sleep(IK_SEARCH_DELAY)
                    continue
            finally:
                connection.close()

            cost_tracker.add_ik_search(1)

            data = json.loads(raw)
            docs = data.get("docs", [])

            result_count = 0
            for doc in docs:
                tid = doc.get("tid")
                if not tid:
                    continue
                title = sanitize_html(doc.get("title", "Untitled"))
                headline = sanitize_html(doc.get("headline", ""))

                try:
                    save_judgment_metadata(
                        tid=tid, title=title,
                        doctype=doc.get("doctype", ""),
                        court_source=doc.get("docsource", ""),
                        publish_date=parse_publish_date(doc.get("publishdate", "")),
                        num_cites=doc.get("numcites", 0) or 0,
                        num_cited_by=doc.get("numcitedby", 0) or 0,
                    )
                except Exception:
                    pass

                save_pipeline_result(job_id, pq["id"], tid, title, headline)
                result_count += 1

            update_pipeline_query(pq["id"], search_completed=True, results_count=result_count)
            completed += 1

            if completed % 5 == 0:
                total_results = _count_pipeline_results(job_id)
                update_research_job(job_id,
                                    total_searches_completed=completed,
                                    total_results_found=total_results)

        except Exception as e:
            logger.warning(f"[{job_id}] Search error for '{ik_query}': {e}")
            update_pipeline_query(pq["id"], search_completed=True, results_count=0)
            completed += 1

        time.sleep(IK_SEARCH_DELAY)

    total_results = _count_pipeline_results(job_id)
    _save_costs(job_id, cost_tracker)
    update_research_job(job_id,
                        total_searches_completed=completed,
                        total_results_found=total_results,
                        searches_completed_at=datetime.now(),
                        current_step="FILTERING",
                        status="FILTERING")
    logger.info(f"[{job_id}] Searches done: {completed}, unique results: {total_results}")


def _step_filter(job_id, job, cost_tracker):
    from db import (update_research_job, get_pipeline_results, bulk_update_relevance)
    import anthropic

    logger.info(f"[{job_id}] Step 4: Relevance filtering")

    all_results = get_pipeline_results(job_id)
    unscored = [r for r in all_results if r["relevance_score"] == 0 and not r["is_relevant"]]

    if not unscored:
        relevant_count = len([r for r in all_results if r["is_relevant"]])
        update_research_job(job_id,
                            total_relevant_judgments=relevant_count,
                            filtering_completed_at=datetime.now(),
                            current_step="FETCHING_DOCS",
                            status="FETCHING_DOCS")
        return

    job = _reload_job(job_id)
    case_summary = _build_case_summary(job)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        update_research_job(job_id, status="FAILED", failed_at=datetime.now(),
                            error_message="ANTHROPIC_API_KEY not configured")
        return

    client = anthropic.Anthropic(api_key=api_key)
    batch_size = 15

    for i in range(0, len(unscored), batch_size):
        batch = unscored[i:i + batch_size]

        judgment_list = ""
        for idx, r in enumerate(batch):
            title = r["title"] or "Untitled"
            headline = r["headline"] or ""
            if len(headline) > 200:
                headline = headline[:200] + "..."
            judgment_list += f"\n[{idx + 1}] TID={r['tid']} | {title}\n    {headline}\n"

        prompt = f"""You are a legal research relevance assessor. Score each judgment's relevance to the litigation case below.

CASE CONTEXT:
{case_summary}

JUDGMENTS TO EVALUATE:
{judgment_list}

For EACH judgment, score relevance 0-10 and provide a one-line reasoning.
10 = directly on point, 0 = completely irrelevant.

RESPOND WITH ONLY THIS JSON (no markdown):
{{
  "scores": [
    {{"tid": <tid_number>, "score": <0-10>, "reasoning": "one line"}}
  ]
}}"""

        try:
            message = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
                timeout=60,
            )

            if hasattr(message, "usage"):
                cost_tracker.add_claude_cost("relevance_filtering", "claude-3-haiku-20240307",
                                              message.usage.input_tokens, message.usage.output_tokens)

            response_text = message.content[0].text.strip()
            if response_text.startswith("```"):
                response_text = response_text.strip("`").strip()
                if response_text.startswith("json"):
                    response_text = response_text[4:].strip()

            scores_data = json.loads(response_text)
            scores_list = scores_data.get("scores", [])

            relevance_updates = []
            for s in scores_list:
                tid = s.get("tid")
                score = s.get("score", 0)
                reasoning = s.get("reasoning", "")
                is_relevant = score >= RELEVANCE_THRESHOLD
                relevance_updates.append((tid, float(score), reasoning, is_relevant))

            if relevance_updates:
                bulk_update_relevance(job_id, relevance_updates)

        except Exception as e:
            logger.warning(f"[{job_id}] Relevance scoring batch failed: {e}")
            relevance_updates = []
            for r in batch:
                relevance_updates.append((r["tid"], 5.0, "scoring failed, included as default", True))
            bulk_update_relevance(job_id, relevance_updates)

        time.sleep(0.5)

    all_results = get_pipeline_results(job_id)
    relevant = [r for r in all_results if r["is_relevant"]]
    relevant.sort(key=lambda x: x["relevance_score"], reverse=True)

    if len(relevant) > MAX_RELEVANT_JUDGMENTS:
        to_exclude = relevant[MAX_RELEVANT_JUDGMENTS:]
        exclude_updates = [(r["tid"], r["relevance_score"], r["relevance_reasoning"], False) for r in to_exclude]
        bulk_update_relevance(job_id, exclude_updates)
        relevant = relevant[:MAX_RELEVANT_JUDGMENTS]

    _save_costs(job_id, cost_tracker)
    update_research_job(job_id,
                        total_relevant_judgments=len(relevant),
                        filtering_completed_at=datetime.now(),
                        current_step="FETCHING_DOCS",
                        status="FETCHING_DOCS")
    logger.info(f"[{job_id}] Filtering done: {len(relevant)} relevant out of {len(all_results)}")


def _step_fetch_docs(job_id, job, cost_tracker):
    from db import (update_research_job, get_pipeline_results,
                    get_cached_judgment, save_judgment_full_text)
    from app import call_ik_api, sanitize_html

    logger.info(f"[{job_id}] Step 5: Fetching documents")

    relevant = get_pipeline_results(job_id, relevant_only=True)

    to_fetch = []
    for r in relevant:
        cached = get_cached_judgment(r["tid"])
        if not cached:
            to_fetch.append(r)

    logger.info(f"[{job_id}] {len(to_fetch)} docs to fetch, {len(relevant) - len(to_fetch)} already cached")

    fetched = 0
    for r in to_fetch:
        try:
            raw = call_ik_api(f"/doc/{r['tid']}/")
            data = json.loads(raw)
            doc_html = sanitize_html(data.get("doc", ""))
            title = sanitize_html(data.get("title", ""))
            save_judgment_full_text(r["tid"], title, doc_html)
            fetched += 1
            cost_tracker.add_ik_document(1)
        except Exception as e:
            logger.warning(f"[{job_id}] Failed to fetch doc {r['tid']}: {e}")

        time.sleep(IK_SEARCH_DELAY)

    _save_costs(job_id, cost_tracker)
    update_research_job(job_id,
                        fetching_completed_at=datetime.now(),
                        current_step="EXTRACTING_GENOMES",
                        status="EXTRACTING_GENOMES")
    logger.info(f"[{job_id}] Fetched {fetched} documents")


def _step_extract_genomes(job_id, job, cost_tracker):
    from db import (update_research_job, get_pipeline_results,
                    get_cached_genome, get_cached_judgment, save_genome,
                    update_pipeline_result)
    from genome_config import (
        APIConfig, build_master_prompt, get_schema_summary, strip_markdown_fences
    )
    from bs4 import BeautifulSoup
    import anthropic

    logger.info(f"[{job_id}] Step 6: Extracting genomes")

    if not APIConfig.is_configured():
        update_research_job(job_id, status="FAILED", failed_at=datetime.now(),
                            error_message="ANTHROPIC_API_KEY not configured")
        return

    relevant = get_pipeline_results(job_id, relevant_only=True)

    to_extract = []
    already_done = 0
    for r in relevant:
        existing = get_cached_genome(r["tid"])
        if existing:
            already_done += 1
            update_pipeline_result(r["id"], genome_extracted=True)
        else:
            to_extract.append(r)

    logger.info(f"[{job_id}] {len(to_extract)} genomes to extract, {already_done} already cached")

    system_prompt = build_master_prompt()
    schema_summary = get_schema_summary()
    client = anthropic.Anthropic(api_key=APIConfig.api_key())

    extracted = 0
    for r in to_extract:
        cached_doc = get_cached_judgment(r["tid"])
        if not cached_doc or not cached_doc.get("full_text_html"):
            logger.warning(f"[{job_id}] No full text for tid {r['tid']}, skipping genome")
            continue

        soup = BeautifulSoup(cached_doc["full_text_html"], "html.parser")
        judgment_text = soup.get_text(separator="\n", strip=True)

        text_len = len(judgment_text)
        if text_len < APIConfig.MIN_JUDGMENT_LENGTH or text_len > APIConfig.MAX_JUDGMENT_LENGTH:
            logger.warning(f"[{job_id}] Text length {text_len} out of range for tid {r['tid']}")
            continue

        citation = cached_doc.get("title", "") or r.get("title", "")
        user_message = f"## SCHEMA SUMMARY\n{schema_summary}\n\n## JUDGMENT TEXT\n\nCitation: {citation}\n\n{judgment_text}"

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                message = client.messages.create(
                    model=APIConfig.model(),
                    max_tokens=APIConfig.max_tokens(),
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                    timeout=600,
                )

                if hasattr(message, "usage"):
                    cost_tracker.add_claude_cost("genome_extraction", APIConfig.model(),
                                                  message.usage.input_tokens, message.usage.output_tokens)
                    _check_cost_limit(job_id, cost_tracker)

                response_text = message.content[0].text
                cleaned = strip_markdown_fences(response_text)

                stop_reason = getattr(message, "stop_reason", None)
                if stop_reason == "max_tokens":
                    logger.warning(f"[{job_id}] Genome for tid {r['tid']} truncated, attempting repair")
                    cleaned = _repair_truncated_json(cleaned)

                genome_data = json.loads(cleaned)

                doc_id = genome_data.get("document_id", "")
                cert_level = None
                durability = None
                try:
                    cert_level = genome_data.get("dimension_6_audit", {}).get("final_certification", {}).get("certification_level")
                    durability = genome_data.get("dimension_4_weaponizable", {}).get("vulnerability_map", {}).get("overall_durability_score")
                except Exception:
                    pass

                save_genome(r["tid"], genome_data, APIConfig.model(), "3.1.0",
                            doc_id, cert_level, durability)
                update_pipeline_result(r["id"], genome_extracted=True)
                extracted += 1
                logger.info(f"[{job_id}] Genome extracted for tid {r['tid']} ({extracted}/{len(to_extract)})")

                _save_costs(job_id, cost_tracker)
                update_research_job(job_id, total_genomes_extracted=already_done + extracted)
                break

            except anthropic.RateLimitError:
                logger.warning(f"[{job_id}] Rate limited during genome extraction, waiting 30s")
                time.sleep(30)
            except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
                if attempt < max_retries:
                    wait_time = 30 * (attempt + 1)
                    logger.warning(f"[{job_id}] Genome timeout for tid {r['tid']} (attempt {attempt+1}), retrying in {wait_time}s")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"[{job_id}] Genome extraction failed for tid {r['tid']} after {max_retries+1} attempts: {e}")
                    break
            except Exception as e:
                logger.warning(f"[{job_id}] Genome extraction failed for tid {r['tid']}: {e}")
                break

        time.sleep(2)

    update_research_job(job_id,
                        total_genomes_extracted=already_done + extracted,
                        genomes_completed_at=datetime.now(),
                        current_step="SYNTHESIZING",
                        status="SYNTHESIZING")
    logger.info(f"[{job_id}] Genome extraction done: {extracted} new + {already_done} cached")


def _step_synthesize(job_id, job, cost_tracker):
    from db import (update_research_job, get_pipeline_results,
                    get_cached_genome, get_question_extraction)
    from synthesis import synthesize_research
    import anthropic

    logger.info(f"[{job_id}] Step 7: Synthesizing research memo")

    job = _reload_job(job_id)

    relevant = get_pipeline_results(job_id, relevant_only=True)

    genomes = []
    for r in relevant:
        g = get_cached_genome(r["tid"])
        if g:
            genome_json = g["genome_json"]
            if isinstance(genome_json, str):
                genome_json = json.loads(genome_json)
            genomes.append({
                "tid": r["tid"],
                "title": r["title"],
                "relevance_score": r["relevance_score"],
                "relevance_reasoning": r["relevance_reasoning"],
                "genome": genome_json,
            })

    q_data = None
    q_ext_id = job.get("question_extraction_id")
    if q_ext_id:
        from db import get_db_connection
        import psycopg2.extras
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM question_extractions WHERE id = %s", (q_ext_id,))
                q_ext = cur.fetchone()
                if q_ext:
                    q_data = q_ext["questions_json"]
                    if isinstance(q_data, str):
                        q_data = json.loads(q_data)
        finally:
            conn.close()

    case_context = {
        "citation": job.get("citation", ""),
        "client_name": job.get("client_name", ""),
        "client_side": job.get("client_side", ""),
        "opposite_party": job.get("opposite_party", ""),
        "court": job.get("court", ""),
        "pleading_type": job.get("pleading_type", ""),
        "reliefs_sought": job.get("reliefs_sought") or [],
    }
    if isinstance(case_context["reliefs_sought"], str):
        try:
            case_context["reliefs_sought"] = json.loads(case_context["reliefs_sought"])
        except Exception:
            case_context["reliefs_sought"] = []

    try:
        memo, usage = synthesize_research(
            pleading_text=job["pleading_text"],
            case_context=case_context,
            genomes=genomes,
            questions_data=q_data,
        )

        if usage:
            cost_tracker.add_claude_cost("synthesis", usage.get("model", "claude-sonnet-4-6"),
                                          usage.get("input_tokens", 0), usage.get("output_tokens", 0))
        _save_costs(job_id, cost_tracker)

        update_research_job(job_id,
                            research_memo=memo,
                            synthesis_completed_at=datetime.now())
        logger.info(f"[{job_id}] Synthesis complete")

    except Exception as e:
        _save_costs(job_id, cost_tracker)
        update_research_job(job_id, status="FAILED", failed_at=datetime.now(),
                            error_message=f"Synthesis failed: {str(e)[:500]}")
        raise


def _deliver_result(job_id):
    import requests
    from db import get_research_job

    job = get_research_job(job_id)
    if not job or not job.get("callback_url"):
        return

    callback_url = job["callback_url"]
    memo = job.get("research_memo")
    if isinstance(memo, str):
        memo = json.loads(memo)

    cost_usd = job.get("cost_estimate_usd") or 0
    cost_breakdown = job.get("cost_breakdown_json")
    if isinstance(cost_breakdown, str):
        try:
            cost_breakdown = json.loads(cost_breakdown)
        except Exception:
            cost_breakdown = {}

    payload = {
        "job_id": str(job_id),
        "status": "COMPLETED",
        "research_memo": memo,
        "stats": {
            "total_questions": job.get("total_questions", 0),
            "queries_executed": job.get("total_queries_generated", 0),
            "judgments_found": job.get("total_results_found", 0),
            "relevant_judgments": job.get("total_relevant_judgments", 0),
            "genomes_extracted": job.get("total_genomes_extracted", 0),
        },
        "cost": {
            "total_usd": round(cost_usd, 4),
            "total_inr": round(cost_usd * 95, 2),
            "breakdown": cost_breakdown or {},
        },
    }

    if job.get("webhook_secret"):
        import hmac
        sig = hmac.new(
            job["webhook_secret"].encode("utf-8"),
            json.dumps(payload).encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        headers = {"X-Webhook-Signature": sig, "Content-Type": "application/json"}
    else:
        headers = {"Content-Type": "application/json"}

    for attempt in range(3):
        try:
            resp = requests.post(callback_url, json=payload, headers=headers, timeout=30)
            if resp.status_code < 400:
                logger.info(f"[{job_id}] Webhook delivered to {callback_url}")
                return
            logger.warning(f"[{job_id}] Webhook attempt {attempt + 1} failed: HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"[{job_id}] Webhook attempt {attempt + 1} error: {e}")

        time.sleep(2 ** attempt * 5)

    logger.error(f"[{job_id}] Webhook delivery failed after 3 attempts")


def _reload_job(job_id):
    from db import get_research_job
    return get_research_job(job_id)


def _count_pipeline_results(job_id):
    from db import get_db_connection
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(DISTINCT tid) FROM pipeline_results WHERE job_id = %s",
                        (str(job_id),))
            return cur.fetchone()[0]
    finally:
        conn.close()


def _prioritize_questions(q_data):
    categories = q_data.get("question_categories", {})
    all_questions = []

    for cat_key, cat_data in categories.items():
        if not isinstance(cat_data, dict):
            continue
        questions = cat_data.get("questions", [])
        cat_id = cat_data.get("category_id", cat_key)
        for q in questions:
            if not isinstance(q, dict):
                continue
            importance = q.get("importance", "MEDIUM")
            all_questions.append({
                "id": q.get("question_id", ""),
                "text": q.get("question", q.get("research_question", q.get("anticipated_argument", ""))),
                "category": cat_id,
                "importance": importance,
                "is_gate": q.get("is_gate_question", False),
                "priority_score": _importance_score(importance, q.get("is_gate_question", False)),
            })

    dt = q_data.get("decision_tree", {})
    gate_questions = dt.get("gate_questions", [])
    gate_ids = set()
    for gq in gate_questions:
        gq_id = gq.get("gate_question_id", "")
        if gq_id:
            gate_ids.add(gq_id)
            existing = [q for q in all_questions if q["id"] == gq_id]
            if not existing:
                all_questions.append({
                    "id": gq_id,
                    "text": gq.get("question_text", ""),
                    "category": "GATE",
                    "importance": "CRITICAL",
                    "is_gate": True,
                    "priority_score": 100,
                })
            else:
                existing[0]["priority_score"] = 100
                existing[0]["is_gate"] = True

    all_questions.sort(key=lambda x: x["priority_score"], reverse=True)

    return all_questions[:MAX_QUESTIONS_TO_PROCESS]


def _importance_score(importance, is_gate):
    scores = {"CRITICAL": 40, "HIGH": 30, "MEDIUM": 20, "LOW": 10}
    base = scores.get(importance, 15)
    if is_gate:
        base += 50
    return base


def _build_case_summary(job):
    parts = []
    if job.get("citation"):
        parts.append(f"Case: {job['citation']}")
    if job.get("pleading_type"):
        parts.append(f"Type: {job['pleading_type']}")
    if job.get("court"):
        parts.append(f"Court: {job['court']}")
    if job.get("client_name") and job.get("client_side"):
        parts.append(f"Client: {job['client_name']} ({job['client_side']})")
    if job.get("opposite_party"):
        parts.append(f"Opposite: {job['opposite_party']}")
    reliefs = job.get("reliefs_sought")
    if reliefs:
        if isinstance(reliefs, str):
            try:
                reliefs = json.loads(reliefs)
            except Exception:
                reliefs = [reliefs]
        if isinstance(reliefs, list):
            parts.append(f"Reliefs: {'; '.join(reliefs[:3])}")

    pleading_excerpt = (job.get("pleading_text") or "")[:500]
    if pleading_excerpt:
        parts.append(f"Pleading excerpt: {pleading_excerpt}...")

    return "\n".join(parts)


def resume_pipeline(job_id):
    from db import get_research_job
    job = get_research_job(job_id)
    if not job:
        return False, "Job not found"

    if job["status"] == "COMPLETED":
        return False, "Job already completed"

    if job["status"] != "FAILED":
        return False, f"Job status is {job['status']}, can only resume FAILED jobs"

    failed_step = job.get("current_step", "EXTRACTING_QUESTIONS")
    from db import update_research_job
    update_research_job(job_id, status=failed_step, failed_at=None, error_message=None)

    start_pipeline(job_id)
    return True, f"Resumed from step: {failed_step}"
