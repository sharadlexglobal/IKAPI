#!/usr/bin/env python3
"""
Test script: Fetch 5 latest Delhi district court judgments from Indian Kanoon,
then extract genomes for all 5 in parallel using AsyncAnthropic.
"""
import asyncio
import http.client
import json
import os
import sys
import time
import urllib.parse

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(__file__))

from genome_config import APIConfig, build_master_prompt, get_schema_summary, strip_markdown_fences
from parallel_claude import run_parallel_calls
from db import (
    init_db,
    save_judgment_metadata,
    save_judgment_full_text,
    get_cached_judgment,
    save_genome,
)

API_HOST = "api.indiankanoon.org"


def call_ik_api(url):
    token = os.environ.get("IK_API_TOKEN", "")
    if not token:
        raise RuntimeError("IK_API_TOKEN not set")
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
            raise Exception(f"IK API error ({status}): {data[:200]}")
        return data
    finally:
        connection.close()


def search_delhi_dc(query="bail", max_results=None):
    max_results = max_results or int(os.environ.get("TEST_NUM_JUDGMENTS", "5"))
    form_input = f"{query} doctypes: delhidc"
    encoded = urllib.parse.quote(form_input)
    url = f"/search/?formInput={encoded}&pagenum=0"
    print(f"  Searching IK: '{form_input}'")
    raw = call_ik_api(url)
    data = json.loads(raw)

    docs = data.get("docs", [])
    results = []
    for doc in docs[:max_results]:
        tid = doc.get("tid")
        title = doc.get("title", "").replace("<b>", "").replace("</b>", "")
        publishdate = doc.get("publishdate", "")
        court = doc.get("docsource", "")
        results.append({
            "tid": tid,
            "title": title,
            "publish_date": publishdate,
            "court": court,
        })

    return results


def fetch_judgment_text(tid):
    cached = get_cached_judgment(tid)
    if cached and cached.get("full_text_html"):
        return cached["full_text_html"], cached.get("title", "")

    raw = call_ik_api(f"/doc/{tid}/")
    data = json.loads(raw)
    doc_html = data.get("doc", "")
    title = data.get("title", "").replace("<b>", "").replace("</b>", "")

    save_judgment_full_text(tid, title, doc_html)
    return doc_html, title


def html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n", strip=True)


def repair_truncated_json(text):
    text = text.rstrip()
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")
    if open_braces > 0 or open_brackets > 0:
        for _ in range(open_brackets):
            text += "]"
        for _ in range(open_braces):
            text += "}"
    return text


def main():
    init_db()

    print("=" * 70)
    print("DELHI DISTRICT COURT — PARALLEL GENOME EXTRACTION TEST")
    print("=" * 70)
    print()

    print("[STEP 1] Searching for 5 latest Delhi DC judgments...")
    judgments = search_delhi_dc(query="bail application", max_results=5)
    print(f"  Found {len(judgments)} judgments:")
    for j in judgments:
        print(f"    TID {j['tid']}: {j['title'][:70]}...")
    print()

    print("[STEP 2] Fetching full text for each judgment...")
    fetch_start = time.time()
    docs = []
    for j in judgments:
        try:
            html, title = fetch_judgment_text(j["tid"])
            text = html_to_text(html)
            text_len = len(text)

            if text_len < APIConfig.MIN_JUDGMENT_LENGTH:
                print(f"    TID {j['tid']}: SKIP — too short ({text_len} chars)")
                continue
            if text_len > APIConfig.MAX_JUDGMENT_LENGTH:
                text = text[:APIConfig.MAX_JUDGMENT_LENGTH]
                print(f"    TID {j['tid']}: TRUNCATED to {APIConfig.MAX_JUDGMENT_LENGTH} chars")

            save_judgment_metadata(j["tid"], title, doctype="delhidc",
                                   court_source=j.get("court", "Delhi District Court"),
                                   publish_date=j.get("publish_date"))

            docs.append({"tid": j["tid"], "title": title or j["title"], "text": text})
            print(f"    TID {j['tid']}: OK — {text_len:,} chars")
        except Exception as e:
            print(f"    TID {j['tid']}: FETCH ERROR — {e}")

    fetch_elapsed = round(time.time() - fetch_start, 1)
    print(f"  Fetched {len(docs)} docs in {fetch_elapsed}s")
    print()

    if not docs:
        print("ERROR: No documents to process. Exiting.")
        sys.exit(1)

    print(f"[STEP 3] Building {len(docs)} parallel genome extraction calls...")
    system_prompt = build_master_prompt()
    schema_summary = get_schema_summary()

    max_tokens = int(os.environ.get("TEST_MAX_TOKENS", str(APIConfig.max_tokens())))

    calls = []
    for doc in docs:
        user_message = (
            f"## SCHEMA SUMMARY\n{schema_summary}\n\n"
            f"## JUDGMENT TEXT\n\nCitation: {doc['title']}\n\n{doc['text']}"
        )
        calls.append({
            "task_id": f"genome_tid_{doc['tid']}",
            "system": system_prompt,
            "user_message": user_message,
            "max_tokens": max_tokens,
            "timeout": 600,
            "parse_json": False,
        })

    print(f"  {len(calls)} calls prepared (model: {APIConfig.model()}, max_tokens: {max_tokens})")
    print()

    print(f"[STEP 4] Firing {len(calls)} parallel Claude API calls...")
    parallel_start = time.time()
    results = asyncio.run(run_parallel_calls(
        calls,
        api_key=APIConfig.api_key(),
        model=APIConfig.model(),
        max_concurrency=5,
    ))
    parallel_elapsed = round(time.time() - parallel_start, 1)

    print()
    print("-" * 70)
    print("EXTRACTION RESULTS")
    print("-" * 70)

    total_input = 0
    total_output = 0
    saved = 0
    individual_times = []

    for r in results:
        tid_str = r["task_id"].replace("genome_tid_", "")
        tid = int(tid_str)
        elapsed = r["elapsed_seconds"]
        individual_times.append(elapsed)
        status = "OK" if r["success"] else "FAIL"

        if not r["success"]:
            print(f"  [{status}] TID {tid} — {elapsed}s — Error: {r.get('error', 'unknown')}")
            continue

        usage = r.get("usage", {})
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        total_input += inp
        total_output += out

        raw_text = r["data"]
        cleaned = strip_markdown_fences(raw_text)
        cleaned = repair_truncated_json(cleaned)

        try:
            genome_data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"  [{status}] TID {tid} — {elapsed}s — JSON parse failed: {e}")
            continue

        doc_id = genome_data.get("document_id", "")
        cert_level = None
        durability = None
        try:
            cert_level = genome_data.get("dimension_6_audit", {}).get(
                "final_certification", {}).get("certification_level")
            durability = genome_data.get("dimension_4_weaponizable", {}).get(
                "vulnerability_map", {}).get("overall_durability_score")
        except Exception:
            pass

        save_genome(tid, genome_data, APIConfig.model(), "3.1.0", doc_id, cert_level, durability)

        try:
            from auto_tagger import tag_genome as _tag
            _tag(tid, genome_data)
        except Exception:
            pass

        saved += 1
        d1_keys = list(genome_data.get("dimension_1_visible", {}).keys())[:3]
        print(f"  [{status}] TID {tid} — {elapsed}s | {inp:,} in / {out:,} out | "
              f"durability={durability} cert={cert_level} D1_keys={d1_keys}")

    print()
    print("-" * 70)
    print("SUMMARY")
    print("-" * 70)

    sequential_est = round(sum(individual_times), 1)
    speedup = round(sequential_est / parallel_elapsed, 2) if parallel_elapsed > 0 else 0

    print(f"  Judgments searched:     {len(judgments)}")
    print(f"  Documents fetched:     {len(docs)}")
    print(f"  Genomes extracted:     {saved}/{len(calls)}")
    print(f"  Parallel wall-clock:   {parallel_elapsed}s")
    print(f"  Sequential estimate:   {sequential_est}s")
    print(f"  Speedup factor:        {speedup}x")
    print(f"  Total input tokens:    {total_input:,}")
    print(f"  Total output tokens:   {total_output:,}")
    print(f"  Model:                 {APIConfig.model()}")
    print()

    if saved == len(calls):
        print(f"VERDICT: All {saved} parallel genome extractions SUCCEEDED")
    elif saved > 0:
        print(f"VERDICT: {saved}/{len(calls)} succeeded — partial success")
    else:
        print(f"VERDICT: All extractions FAILED")

    print("=" * 70)


if __name__ == "__main__":
    main()
