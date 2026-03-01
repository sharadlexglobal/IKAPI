#!/usr/bin/env python3
"""
Test script: Fires 6 parallel Claude Sonnet 4.6 API calls and measures timing.
Compares wall-clock time of parallel vs estimated sequential time.
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from parallel_claude import run_parallel_calls

SYSTEM_PROMPT = "You are a helpful assistant. Respond with valid JSON only."

TEST_CALLS = [
    {
        "task_id": f"task_{i+1}",
        "system": SYSTEM_PROMPT,
        "user_message": prompt,
        "max_tokens": 1024,
        "parse_json": True,
    }
    for i, prompt in enumerate([
        'List 3 fundamental rights in the Indian Constitution. Respond as: {"rights": ["...", "...", "..."]}',
        'Name 3 landmark Indian Supreme Court cases. Respond as: {"cases": ["...", "...", "..."]}',
        'List 3 types of writs under Article 226. Respond as: {"writs": ["...", "...", "..."]}',
        'Name 3 sections of the Indian Penal Code related to property offenses. Respond as: {"sections": ["...", "...", "..."]}',
        'List 3 grounds for bail in Indian criminal law. Respond as: {"grounds": ["...", "...", "..."]}',
        'Name 3 courts in the Indian judicial hierarchy. Respond as: {"courts": ["...", "...", "..."]}',
    ])
]


async def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    print("=" * 60)
    print("PARALLEL CLAUDE API TEST — 6 Concurrent Calls")
    print(f"Model: claude-sonnet-4-6")
    print("=" * 60)
    print()

    print(f"Launching {len(TEST_CALLS)} parallel requests...")
    start = time.time()
    results = await run_parallel_calls(
        TEST_CALLS,
        api_key=api_key,
        model="claude-sonnet-4-6",
        max_concurrency=6,
    )
    wall_clock = round(time.time() - start, 2)

    print()
    print("-" * 60)
    print("RESULTS")
    print("-" * 60)

    total_input_tokens = 0
    total_output_tokens = 0
    individual_times = []

    for r in results:
        status = "OK" if r["success"] else "FAIL"
        elapsed = r["elapsed_seconds"]
        individual_times.append(elapsed)

        if r["success"]:
            usage = r.get("usage", {})
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            total_input_tokens += inp
            total_output_tokens += out
            data_preview = json.dumps(r["data"])[:80]
            print(f"  [{status}] {r['task_id']:8s} — {elapsed:5.1f}s | {inp:4d} in / {out:4d} out | {data_preview}")
        else:
            print(f"  [{status}] {r['task_id']:8s} — {elapsed:5.1f}s | Error: {r.get('error', 'unknown')}")

    print()
    print("-" * 60)
    print("SUMMARY")
    print("-" * 60)

    succeeded = sum(1 for r in results if r["success"])
    failed = sum(1 for r in results if not r["success"])
    sequential_est = round(sum(individual_times), 2)
    speedup = round(sequential_est / wall_clock, 2) if wall_clock > 0 else 0

    print(f"  Total calls:           {len(results)}")
    print(f"  Succeeded:             {succeeded}")
    print(f"  Failed:                {failed}")
    print(f"  Wall-clock time:       {wall_clock}s")
    print(f"  Sum of individual:     {sequential_est}s (estimated sequential)")
    print(f"  Speedup factor:        {speedup}x")
    print(f"  Total input tokens:    {total_input_tokens}")
    print(f"  Total output tokens:   {total_output_tokens}")
    print()

    if failed == 0:
        print("VERDICT: All 6 parallel calls SUCCEEDED")
    else:
        print(f"VERDICT: {failed} call(s) FAILED — check rate limits or API key")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
