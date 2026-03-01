#!/usr/bin/env python3
"""
Extract genomes for Delhi DC judgments already stored in DB.
Processes sequentially, saves each genome immediately after extraction.
Writes progress to a status file for monitoring.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from bs4 import BeautifulSoup
import anthropic

from genome_config import APIConfig, build_master_prompt, get_schema_summary, strip_markdown_fences
from db import init_db, get_cached_judgment, get_cached_genome, save_genome

STATUS_FILE = "/home/runner/workspace/dc_extraction_status.txt"

TIDS = [166935227, 50123327, 164120724, 10001052, 65675427]


def write_status(msg):
    with open(STATUS_FILE, "a", buffering=1) as f:
        f.write(msg + "\n")
    print(msg, flush=True)


def repair_truncated_json(text):
    text = text.rstrip()
    opens = text.count("{") - text.count("}")
    brackets = text.count("[") - text.count("]")
    for _ in range(brackets):
        text += "]"
    for _ in range(opens):
        text += "}"
    return text


def main():
    init_db()
    with open(STATUS_FILE, "w") as f:
        f.write("GENOME EXTRACTION STARTED\n")

    system_prompt = build_master_prompt()
    schema_summary = get_schema_summary()
    client = anthropic.Anthropic(api_key=APIConfig.api_key())

    for i, tid in enumerate(TIDS):
        existing = get_cached_genome(tid)
        if existing:
            write_status(f"[{i+1}/{len(TIDS)}] TID {tid}: ALREADY HAS GENOME — skipping")
            continue

        cached = get_cached_judgment(tid)
        if not cached or not cached.get("full_text_html"):
            write_status(f"[{i+1}/{len(TIDS)}] TID {tid}: NO FULL TEXT — skipping")
            continue

        soup = BeautifulSoup(cached["full_text_html"], "html.parser")
        text = soup.get_text(separator="\n", strip=True)
        citation = cached.get("title", "") or f"TID {tid}"

        write_status(f"[{i+1}/{len(TIDS)}] TID {tid}: Extracting genome ({len(text):,} chars)...")

        user_message = f"## SCHEMA SUMMARY\n{schema_summary}\n\n## JUDGMENT TEXT\n\nCitation: {citation}\n\n{text}"

        start = time.time()
        try:
            message = client.messages.create(
                model=APIConfig.model(),
                max_tokens=APIConfig.max_tokens(),
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                timeout=600,
            )

            elapsed = round(time.time() - start, 1)
            response_text = message.content[0].text
            cleaned = strip_markdown_fences(response_text)

            stop_reason = getattr(message, "stop_reason", None)
            if stop_reason == "max_tokens":
                write_status(f"  Truncated at max_tokens, attempting repair...")
                cleaned = repair_truncated_json(cleaned)

            genome_data = json.loads(cleaned)

            doc_id = genome_data.get("document_id", "")
            cert_level = None
            durability = None
            try:
                cert_level = genome_data.get("dimension_6_audit", {}).get("final_certification", {}).get("certification_level")
                durability = genome_data.get("dimension_4_weaponizable", {}).get("vulnerability_map", {}).get("overall_durability_score")
            except Exception:
                pass

            save_genome(tid, genome_data, APIConfig.model(), "3.1.0", doc_id, cert_level, durability)

            try:
                from auto_tagger import tag_genome as _tag
                _tag(tid, genome_data)
            except Exception:
                pass

            inp = message.usage.input_tokens if hasattr(message, "usage") else 0
            out = message.usage.output_tokens if hasattr(message, "usage") else 0
            write_status(f"  DONE in {elapsed}s | {inp:,} in / {out:,} out | durability={durability} cert={cert_level}")

        except Exception as e:
            elapsed = round(time.time() - start, 1)
            write_status(f"  FAILED after {elapsed}s: {e}")

    write_status("ALL DONE")


if __name__ == "__main__":
    main()
