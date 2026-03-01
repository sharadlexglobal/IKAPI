"""
End-to-end test for the Superfast Expressway.
Tests the sync API endpoint with a sample bail application.
"""
import json
import os
import sys
import time
import requests

BASE_URL = "http://localhost:5000"

SAMPLE_PLEADING = """
IN THE COURT OF SESSIONS JUDGE, SAKET COURTS, NEW DELHI

BAIL APPLICATION NO. ___/2026

IN THE MATTER OF:
State vs. Rajesh Kumar

BAIL APPLICATION UNDER SECTION 439 OF THE CODE OF CRIMINAL PROCEDURE, 1973

The applicant/accused Rajesh Kumar, son of Shri Ram Kumar, resident of B-45, Lajpat Nagar, New Delhi, most respectfully submits as under:

1. That the applicant has been falsely implicated in FIR No. 234/2025 registered at PS Saket, New Delhi under Sections 420, 468 and 471 of the Indian Penal Code, 1860.

2. That the applicant is in judicial custody since 15.01.2026 and his bail application was rejected by the learned Metropolitan Magistrate on 20.01.2026.

3. That the investigation in the present case is complete and the charge sheet has already been filed. The applicant is no longer required for the purpose of investigation.

4. That the applicant is a first-time offender with no prior criminal record. He is a permanent resident of Delhi with deep roots in the community and there is no flight risk.

5. That the alleged offence under Section 420 IPC is punishable with imprisonment which may extend to seven years, and the applicant has already undergone more than 45 days of incarceration.

6. That the complainant himself is involved in multiple civil disputes with the applicant regarding a property transaction, and the present FIR has been lodged with mala fide intentions to harass the applicant.

7. That the applicant undertakes to abide by all conditions imposed by this Hon'ble Court and shall not tamper with evidence or influence witnesses.

8. That the applicant is the sole breadwinner of his family and his continued detention is causing extreme hardship to his wife, two minor children, and aged parents who are dependent on him.

PRAYER:
It is most respectfully prayed that this Hon'ble Court may be pleased to:
(a) Grant regular bail to the applicant in FIR No. 234/2025 registered at PS Saket under Sections 420, 468 and 471 IPC;
(b) Pass any other order as this Hon'ble Court may deem fit and proper in the interest of justice.
"""

def test_expressway():
    print("=" * 70)
    print("SUPERFAST EXPRESSWAY — END-TO-END TEST")
    print("=" * 70)

    payload = {
        "pleading_text": SAMPLE_PLEADING,
        "pleading_type": "BAIL_APPLICATION",
        "court": "Delhi District Court",
        "max_judgments": 5,
    }

    print(f"\nSending bail application ({len(SAMPLE_PLEADING)} chars) to expressway...")
    print(f"Max judgments: {payload['max_judgments']}")
    print()

    start = time.time()
    try:
        resp = requests.post(
            f"{BASE_URL}/api/expressway/research",
            json=payload,
            timeout=120,
        )
    except requests.exceptions.Timeout:
        print("TIMEOUT — request took longer than 120 seconds")
        return
    except requests.exceptions.ConnectionError:
        print("CONNECTION ERROR — is the server running?")
        return

    elapsed = round(time.time() - start, 2)
    print(f"Response received in {elapsed}s (status {resp.status_code})")
    print()

    if resp.status_code != 200:
        print(f"ERROR: {resp.text[:500]}")
        return

    data = resp.json()

    if not data.get("success"):
        print(f"FAILED: {data.get('error', 'Unknown error')}")
        return

    print(f"Execution time: {data.get('execution_time_seconds')}s")
    print(f"Step times: {json.dumps(data.get('step_times', {}), indent=2)}")
    print()

    queries = data.get("queries_used", [])
    print(f"QUERIES GENERATED: {len(queries)}")
    for i, q in enumerate(queries):
        print(f"  Q{i+1}: {q.get('query', '')[:80]}")
        print(f"       doctype={q.get('doctype', '')} | {q.get('rationale', '')[:60]}")
    print()

    full_texts = data.get("full_texts", [])
    print(f"FULL TEXTS RETRIEVED: {len(full_texts)}")
    for j in full_texts:
        print(f"  TID {j['tid']}: {j['title'][:60]}...")
        print(f"       Court: {j.get('court', '?')} | Cited by: {j.get('cited_by', 0)} | {j.get('text_length', 0)} chars")
    print()

    extracts = data.get("relevant_extracts", [])
    print(f"RELEVANT EXTRACTS: {len(extracts)}")
    for j in extracts:
        para_count = len(j.get("relevant_paragraphs", []))
        print(f"  TID {j['tid']}: {para_count} relevant paragraphs (of {j.get('total_paragraphs', '?')} total)")
    print()

    drafted = data.get("drafted_paragraphs")
    if drafted:
        paras = drafted.get("drafted_paragraphs", [])
        print(f"DRAFTED PARAGRAPHS: {len(paras)}")
        for p in paras:
            print(f"\n  --- Paragraph {p.get('paragraph_number', '?')} (confidence: {p.get('confidence', '?')}) ---")
            print(f"  Proposition: {p.get('proposition', '')[:100]}")
            print(f"  Cases cited: {', '.join(p.get('cases_cited', []))}")
            text = p.get("text", "")
            print(f"  Text ({len(text)} chars):")
            for line in text.split(". "):
                print(f"    {line.strip()}.")
        if drafted.get("drafting_notes"):
            print(f"\n  Drafting notes: {drafted['drafting_notes'][:200]}")
    else:
        print("DRAFTED PARAGRAPHS: None (drafting may have failed)")
        if data.get("drafting_error"):
            print(f"  Error: {data['drafting_error']}")

    print()
    usage = data.get("token_usage", {})
    print(f"TOKEN USAGE:")
    print(f"  Input:  {usage.get('total_input_tokens', 0):,}")
    print(f"  Output: {usage.get('total_output_tokens', 0):,}")
    print(f"  Cost:   ${usage.get('total_cost_usd', 0):.4f}")
    print()
    print("=" * 70)
    print(f"TEST COMPLETE — Total wall-clock: {elapsed}s")
    print("=" * 70)

    with open("/home/runner/workspace/expressway_test_result.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nFull result saved to expressway_test_result.json")


if __name__ == "__main__":
    test_expressway()
