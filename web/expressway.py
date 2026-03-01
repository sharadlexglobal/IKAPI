"""
Superfast Expressway — bypasses genome extraction pipeline.
Receives a legal pleading, finds relevant judgments via IK API,
and returns full texts + relevant paragraphs + ready-made legal paragraphs.
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import time
import urllib.parse
from typing import Any

import aiohttp
import anthropic

from expressway_prompts import QUERY_EXTRACTION_PROMPT, LEGAL_PARA_DRAFTING_PROMPT

logger = logging.getLogger(__name__)

IK_API_HOST = "https://api.indiankanoon.org"
HAIKU_MODEL = "claude-3-haiku-20240307"
SONNET_MODEL = "claude-sonnet-4-6"

COST_HAIKU_INPUT = 0.25 / 1_000_000
COST_HAIKU_OUTPUT = 1.25 / 1_000_000
COST_SONNET_INPUT = 3.0 / 1_000_000
COST_SONNET_OUTPUT = 15.0 / 1_000_000


def _strip_markdown_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    return text


def _strip_html_tags(html: str) -> str:
    if not html:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', html)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def _extract_paragraphs_from_html(html: str) -> list[dict]:
    if not html:
        return []
    paragraphs = []
    parts = re.split(r'<p\b[^>]*>', html)
    for i, part in enumerate(parts):
        text = re.sub(r'</p>.*', '', part, flags=re.DOTALL)
        text = _strip_html_tags(text).strip()
        if len(text) > 30:
            para_match = re.match(r'^(\d+)\.\s+', text)
            para_num = int(para_match.group(1)) if para_match else i
            paragraphs.append({"para_num": para_num, "text": text})
    return paragraphs


def pleading_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


async def _ik_api_call(session: aiohttp.ClientSession, path: str, token: str) -> dict | str | None:
    headers = {
        "Authorization": f"Token {token}",
        "Accept": "application/json",
    }
    url = f"{IK_API_HOST}{path}"
    try:
        async with session.post(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            text = await resp.text()
            if resp.status >= 400:
                logger.warning(f"[expressway] IK API error {resp.status} for {path}")
                return None
            return json.loads(text)
    except Exception as e:
        logger.error(f"[expressway] IK API call failed for {path}: {e}")
        return None


def _generate_queries_sync(pleading_text: str, pleading_type: str = "") -> list[dict]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    client = anthropic.Anthropic(api_key=api_key)
    user_msg = f"PLEADING TYPE: {pleading_type or 'Not specified'}\n\nPLEADING TEXT:\n{pleading_text[:50000]}"

    try:
        message = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=2000,
            system=QUERY_EXTRACTION_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            timeout=30,
        )
        response_text = message.content[0].text.strip()
        cleaned = _strip_markdown_json(response_text)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            cleaned = re.sub(r',\s*}', '}', cleaned)
            cleaned = re.sub(r',\s*]', ']', cleaned)
            cleaned = re.sub(r'[\x00-\x1f]', ' ', cleaned)
            parsed = json.loads(cleaned)
        queries = parsed.get("queries", [])
        usage = {
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
            "cost_usd": (message.usage.input_tokens * COST_HAIKU_INPUT +
                         message.usage.output_tokens * COST_HAIKU_OUTPUT),
        }
        logger.info(f"[expressway] Generated {len(queries)} queries via Haiku")
        return queries, usage
    except Exception as e:
        logger.error(f"[expressway] Query generation failed: {e}")
        provisions = re.findall(r'[Ss]ection\s+\d+[A-Za-z]?\s+(?:of\s+)?(?:the\s+)?\w+', pleading_text[:10000])
        fallback = []
        for p in provisions[:3]:
            fallback.append({"query": f'"{p}"', "doctype": "supremecourt", "sort": "mostcited", "rationale": "fallback"})
        if not fallback:
            words = pleading_text[:200].split()[:10]
            fallback.append({"query": " ".join(words), "doctype": "", "sort": "mostcited", "rationale": "fallback"})
        return fallback, {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0}


async def _search_ik_parallel(queries: list[dict], token: str, max_judgments: int = 15) -> list[dict]:
    all_docs = {}

    async with aiohttp.ClientSession() as session:
        tasks = []
        for q in queries:
            form_input = q.get("query", "")
            doctype = q.get("doctype", "")
            sort = q.get("sort", "")
            if doctype:
                form_input += f" doctypes: {doctype}"
            if sort:
                form_input += f" sortby: {sort}"
            encoded = urllib.parse.quote_plus(form_input)
            for page in range(2):
                path = f"/search/?formInput={encoded}&pagenum={page}"
                tasks.append(_ik_api_call(session, path, token))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception) or result is None:
                continue
            if isinstance(result, dict) and "docs" in result:
                for doc in result["docs"]:
                    tid = doc.get("tid")
                    if tid and tid not in all_docs:
                        all_docs[tid] = {
                            "tid": tid,
                            "title": _strip_html_tags(doc.get("title", "")),
                            "numcitedby": doc.get("numcitedby", 0) or 0,
                            "docsource": doc.get("docsource", ""),
                            "publishdate": doc.get("publishdate", ""),
                            "headline": _strip_html_tags(doc.get("headline", "")),
                        }

    ranked = sorted(all_docs.values(), key=lambda d: d["numcitedby"], reverse=True)
    top = ranked[:max_judgments]
    logger.info(f"[expressway] Found {len(all_docs)} unique judgments, taking top {len(top)}")
    return top


async def _fetch_docs_parallel(
    judgments: list[dict],
    queries: list[dict],
    token: str,
) -> list[dict]:
    async with aiohttp.ClientSession() as session:
        doc_tasks = []
        fragment_tasks = []

        for j in judgments:
            tid = j["tid"]
            doc_tasks.append(_ik_api_call(session, f"/doc/{tid}/", token))

        query_text = queries[0].get("query", "") if queries else ""
        if query_text:
            encoded_q = urllib.parse.quote_plus(query_text)
            for j in judgments:
                tid = j["tid"]
                fragment_tasks.append(
                    _ik_api_call(session, f"/docfragment/{tid}/?formInput={encoded_q}", token)
                )

        doc_results = await asyncio.gather(*doc_tasks, return_exceptions=True)
        frag_results = await asyncio.gather(*fragment_tasks, return_exceptions=True) if fragment_tasks else [None] * len(judgments)

        enriched = []
        for i, j in enumerate(judgments):
            doc_data = doc_results[i] if i < len(doc_results) else None
            frag_data = frag_results[i] if i < len(frag_results) else None

            if isinstance(doc_data, Exception) or doc_data is None:
                continue

            full_text = ""
            if isinstance(doc_data, dict):
                full_text = doc_data.get("doc", "")
                j["title"] = _strip_html_tags(doc_data.get("title", j.get("title", "")))
                j["numcitedby"] = doc_data.get("numcitedby", j.get("numcitedby", 0))
                j["author"] = doc_data.get("author", "")

            plain_text = _strip_html_tags(full_text)
            paragraphs = _extract_paragraphs_from_html(full_text)

            fragment_paras = []
            if isinstance(frag_data, dict):
                frag_html = frag_data.get("fragment", "")
                if frag_html:
                    fragment_paras = _extract_paragraphs_from_html(frag_html)

            enriched.append({
                "tid": j["tid"],
                "title": j.get("title", ""),
                "docsource": j.get("docsource", ""),
                "publishdate": j.get("publishdate", ""),
                "numcitedby": j.get("numcitedby", 0),
                "author": j.get("author", ""),
                "full_text": plain_text,
                "full_text_length": len(plain_text),
                "paragraphs": paragraphs,
                "relevant_fragments": fragment_paras,
            })

        logger.info(f"[expressway] Fetched {len(enriched)} full documents")
        return enriched


def _estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1


def _draft_legal_paragraphs(pleading_json: dict, enriched_judgments: list[dict]) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    client = anthropic.Anthropic(api_key=api_key)

    MAX_TOTAL_TOKENS = 150000
    SYSTEM_PROMPT_TOKENS = _estimate_tokens(LEGAL_PARA_DRAFTING_PROMPT)
    PLEADING_TOKENS = _estimate_tokens(json.dumps(pleading_json, ensure_ascii=False))
    OVERHEAD_TOKENS = 5000
    available_for_judgments = MAX_TOTAL_TOKENS - SYSTEM_PROMPT_TOKENS - PLEADING_TOKENS - OVERHEAD_TOKENS

    sorted_judgments = sorted(enriched_judgments, key=lambda j: j.get("numcitedby", 0), reverse=True)

    judgment_summaries = []
    tokens_used = 0
    for j in sorted_judgments:
        relevant_frags = j.get("relevant_fragments", [])[:20]
        relevant_text = json.dumps(relevant_frags, ensure_ascii=False) if relevant_frags else ""
        relevant_tokens = _estimate_tokens(relevant_text)

        remaining = available_for_judgments - tokens_used
        if remaining <= 0:
            break

        meta_tokens = 200
        text_budget_tokens = remaining - meta_tokens - relevant_tokens
        if text_budget_tokens < 500:
            text_budget_tokens = 500

        max_chars = text_budget_tokens * 4
        full_text = j["full_text"][:max_chars]

        summary = {
            "tid": j["tid"],
            "title": j["title"],
            "court": j["docsource"],
            "date": j["publishdate"],
            "judge": j.get("author", ""),
            "cited_by": j["numcitedby"],
            "full_text": full_text,
        }
        if relevant_frags:
            summary["relevant_paragraphs"] = relevant_frags
        judgment_summaries.append(summary)

        entry_tokens = _estimate_tokens(json.dumps(summary, ensure_ascii=False))
        tokens_used += entry_tokens

    logger.info(f"[expressway] Drafting with {len(judgment_summaries)}/{len(enriched_judgments)} judgments, "
                f"~{tokens_used} judgment tokens (budget {available_for_judgments})")

    user_msg = json.dumps({
        "pleading": pleading_json,
        "judgments": judgment_summaries,
        "instruction": "Write 2-3 ready-made legal paragraphs citing these judgments accurately. Each paragraph should be insertable directly into the pleading document."
    }, ensure_ascii=False)

    try:
        message = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=4000,
            system=LEGAL_PARA_DRAFTING_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            timeout=600,
        )
        response_text = message.content[0].text.strip()
        cleaned = _strip_markdown_json(response_text)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            cleaned = re.sub(r',\s*}', '}', cleaned)
            cleaned = re.sub(r',\s*]', ']', cleaned)
            cleaned = re.sub(r'[\x00-\x1f]', ' ', cleaned)
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                brace_start = cleaned.find('{')
                brace_end = cleaned.rfind('}')
                if brace_start >= 0 and brace_end > brace_start:
                    parsed = json.loads(cleaned[brace_start:brace_end + 1])
                else:
                    raise
        usage = {
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
            "cost_usd": (message.usage.input_tokens * COST_SONNET_INPUT +
                         message.usage.output_tokens * COST_SONNET_OUTPUT),
        }
        logger.info(f"[expressway] Drafted {len(parsed.get('drafted_paragraphs', []))} paragraphs "
                     f"({message.usage.input_tokens} in / {message.usage.output_tokens} out)")
        return {"result": parsed, "usage": usage}
    except Exception as e:
        logger.error(f"[expressway] Paragraph drafting failed: {e}")
        return {"result": None, "usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0}, "error": str(e)}


def run_expressway(pleading_json: dict, max_judgments: int = 15) -> dict:
    start_time = time.time()

    pleading_text = pleading_json.get("pleading_text", "")
    pleading_type = pleading_json.get("pleading_type", "")

    if not pleading_text or len(pleading_text) < 100:
        return {"error": "pleading_text must be at least 100 characters", "success": False}

    ik_token = os.environ.get("IK_API_TOKEN", "")
    if not ik_token:
        return {"error": "IK_API_TOKEN not configured", "success": False}

    logger.info(f"[expressway] Starting research — pleading {len(pleading_text)} chars, max {max_judgments} judgments")

    step_times = {}

    t0 = time.time()
    queries, query_usage = _generate_queries_sync(pleading_text, pleading_type)
    step_times["query_generation"] = round(time.time() - t0, 2)
    logger.info(f"[expressway] Step 1 (queries): {step_times['query_generation']}s — {len(queries)} queries")

    t0 = time.time()
    search_results = asyncio.run(_search_ik_parallel(queries, ik_token, max_judgments))
    step_times["ik_search"] = round(time.time() - t0, 2)
    logger.info(f"[expressway] Step 2 (search): {step_times['ik_search']}s — {len(search_results)} results")

    if not search_results:
        elapsed = round(time.time() - start_time, 2)
        return {
            "success": False,
            "error": "No judgments found for the given pleading",
            "queries_used": queries,
            "execution_time_seconds": elapsed,
        }

    t0 = time.time()
    enriched = asyncio.run(_fetch_docs_parallel(search_results, queries, ik_token))
    step_times["doc_fetch"] = round(time.time() - t0, 2)
    logger.info(f"[expressway] Step 3 (fetch): {step_times['doc_fetch']}s — {len(enriched)} docs fetched")

    full_texts = []
    relevant_extracts = []
    for j in enriched:
        full_texts.append({
            "tid": j["tid"],
            "title": j["title"],
            "court": j["docsource"],
            "date": j["publishdate"],
            "judge": j.get("author", ""),
            "cited_by": j["numcitedby"],
            "full_text": j["full_text"],
            "text_length": j["full_text_length"],
        })
        relevant_extracts.append({
            "tid": j["tid"],
            "title": j["title"],
            "metadata": {
                "court": j["docsource"],
                "date": j["publishdate"],
                "judge": j.get("author", ""),
                "cited_by": j["numcitedby"],
            },
            "relevant_paragraphs": j.get("relevant_fragments", [])[:15],
            "total_paragraphs": len(j.get("paragraphs", [])),
        })

    t0 = time.time()
    draft_result = _draft_legal_paragraphs(pleading_json, enriched)
    step_times["paragraph_drafting"] = round(time.time() - t0, 2)
    logger.info(f"[expressway] Step 4 (draft): {step_times['paragraph_drafting']}s")

    total_input = query_usage.get("input_tokens", 0) + draft_result["usage"].get("input_tokens", 0)
    total_output = query_usage.get("output_tokens", 0) + draft_result["usage"].get("output_tokens", 0)
    total_cost = query_usage.get("cost_usd", 0) + draft_result["usage"].get("cost_usd", 0)

    elapsed = round(time.time() - start_time, 2)

    result = {
        "success": True,
        "execution_time_seconds": elapsed,
        "step_times": step_times,
        "queries_used": [{"query": q.get("query", ""), "doctype": q.get("doctype", ""), "rationale": q.get("rationale", "")} for q in queries],
        "total_judgments_found": len(enriched),
        "full_texts": full_texts,
        "relevant_extracts": relevant_extracts,
        "drafted_paragraphs": draft_result.get("result"),
        "token_usage": {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost_usd": round(total_cost, 4),
        },
    }

    if draft_result.get("error"):
        result["drafting_error"] = draft_result["error"]

    logger.info(f"[expressway] COMPLETE in {elapsed}s — {len(enriched)} judgments, "
                f"${round(total_cost, 4)} cost, {total_input}+{total_output} tokens")

    return result
