"""
Test script — exercises all Claude API calls used in the CourtCraft.ai pipeline.
Tests: Question Extraction (Sonnet 4), Query Generation (Haiku), Relevance Filtering (Haiku),
       Genome Extraction (Sonnet 4), Synthesis (Sonnet 4).
"""
import json
import os
import sys
import time
import traceback

import anthropic

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from genome_config import (
    APIConfig, build_question_extractor_prompt, get_question_schema_summary,
    build_master_prompt, get_schema_summary, strip_markdown_fences
)
from query_generator import QUERY_GEN_SYSTEM

PLEADING_EXCERPT = """IN THE HIGH COURT OF JUDICATURE AT BOMBAY
APPEAL NO. ___ OF 2026 (Under Section 117A of the Patents Act, 1970)
HUAWEI TECHNOLOGIES CO., LTD. vs THE ASSISTANT CONTROLLER OF PATENTS & DESIGNS

The present Appeal challenges the Refusal Order dated 29.01.2026 refusing Patent Application
No. 202227010211 titled "COMMUNICATION METHOD, APPARATUS, AND SYSTEM". The invention relates to
AKMA (Authentication and Key Management for Applications) services in 5G/6G communication networks.

The invention integrates AKMA authentication within the primary registration procedure of a terminal
device, eliminating the need for a separate AKMA authentication procedure. The key innovation is that
an AKMA temporary identifier is generated and sent during registration itself.

Grounds: (A) Appeal maintainable under Section 117A(2). (B) Refusal order is unreasoned and procedurally
defective. (C) D3 does not anticipate the claimed invention — Figure 6.4.2.2.2-1 shows AKMA is performed
separately from registration. (D) Invention involves technical advance under Section 2(1)(ja).
(E) Not excluded under Section 3(k) — provides tangible technical effect in 4G/5G/6G networks.
(F) Controller failed to consider amended claims under Sections 15, 57(6), 59(1), 80.

Reliance: The General Tire v. Firestone [1972] R.P.C. 457; Lava International v. Ericsson 2024:DHC:2698;
Agfa NV v. ACPD 2023:DHC:4030; Agriboard v. DCPD 2022:DHC:1206; Ab Initio v. ACPD 2024:DHC:708."""

SAMPLE_JUDGMENT_TEXT = """IN THE HIGH COURT OF DELHI AT NEW DELHI
Decided on: 15.03.2024
Ab Initio Technology LLC v. Assistant Controller of Patents and Design

The petitioner challenged the refusal of patent application on the ground that the invention was
a computer programme per se under Section 3(k) of the Patents Act, 1970.

The Court observed that Section 3(k) excludes only "computer programmes per se" and not inventions
that use computer programs to achieve a technical effect. The Court held that a system or method
enabling more efficient and faster output results in a technical effect and is therefore not barred
by Section 3(k). The mere fact that an invention involves algorithms or computational steps does
not automatically render it unpatentable.

The Court further held that the Controller must examine whether the invention produces a technical
contribution that goes beyond the normal physical interactions between a programme and the computer.
An invention that operates on specific hardware elements and produces tangible improvements in
performance falls outside the Section 3(k) exclusion.

ORDER: The refusal order is set aside. The matter is remitted to the Controller for fresh examination."""

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results_log = []


def run_test(name, fn):
    print(f"\n{'='*70}")
    print(f"TEST: {name}")
    print(f"{'='*70}")
    start = time.time()
    try:
        fn()
        elapsed = time.time() - start
        print(f"\n  [{PASS}] {name} ({elapsed:.1f}s)")
        results_log.append((name, True, elapsed, None))
    except Exception as e:
        elapsed = time.time() - start
        tb = traceback.format_exc()
        print(f"\n  [{FAIL}] {name} ({elapsed:.1f}s)")
        print(f"  Error: {e}")
        print(f"  Traceback:\n{tb}")
        results_log.append((name, False, elapsed, str(e)))


def test_1_question_extraction():
    print(f"  Model: {APIConfig.model()}")

    system_prompt = build_question_extractor_prompt()
    schema_summary = get_question_schema_summary()

    user_message = (
        f"## OUTPUT SCHEMA\n{schema_summary}\n\n"
        f"## PLEADING TYPE: PATENT_APPEAL\n## CITATION: Huawei v. ACPD, Appeal 2026\n\n"
        f"## PLEADING TEXT\n\n{PLEADING_EXCERPT}"
    )

    client = anthropic.Anthropic(api_key=APIConfig.api_key())
    message = client.messages.create(
        model=APIConfig.model(),
        max_tokens=8000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        timeout=180,
    )

    print(f"  Input tokens:  {message.usage.input_tokens}")
    print(f"  Output tokens: {message.usage.output_tokens}")
    print(f"  Stop reason:   {message.stop_reason}")

    response_text = message.content[0].text
    cleaned = strip_markdown_fences(response_text)
    data = json.loads(cleaned)

    total_q = data.get("extraction_summary", {}).get("total_questions", 0)
    print(f"  Questions extracted: {total_q}")
    assert total_q > 0, f"Expected questions > 0, got {total_q}"

    categories = data.get("categories", [])
    print(f"  Categories: {len(categories)}")
    for cat in categories[:3]:
        cat_name = cat.get("category_name", "?")
        q_count = len(cat.get("questions", []))
        print(f"    - {cat_name}: {q_count} questions")

    gate_qs = data.get("gate_questions", [])
    print(f"  Gate questions: {len(gate_qs)}")
    for gq in gate_qs[:2]:
        print(f"    - {gq.get('question', '?')[:80]}")


def test_2_query_generation():
    print("  Model: claude-3-haiku-20240307")

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    questions = [
        {"question_id": "Q1", "category": "Jurisdictional",
         "text": "Whether appeal under Section 117A(2) of the Patents Act 1970 is maintainable?"},
        {"question_id": "Q2", "category": "Substantive",
         "text": "Whether D3 anticipates Claim 16 under Section 2(1)(j)?"},
        {"question_id": "Q3", "category": "Substantive",
         "text": "Whether invention is excluded under Section 3(k) as computer programme per se?"},
    ]

    batch_prompt = (
        "Generate Indian Kanoon search queries for each question.\n"
        "CASE CONTEXT: Court: Bombay High Court; Type: PATENT_APPEAL\n\n"
        "RESPOND WITH ONLY THIS JSON (no markdown):\n"
        '{"results": {"<qid>": {"queries": [{"ik_query": "...", "doctype": "...", "sort": "mostcited", "rationale": "..."}]}}}\n\n'
        "QUESTIONS:\n"
    )
    for q in questions:
        batch_prompt += f"[{q['question_id']}] ({q['category']}) {q['text']}\n"

    message = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=2000,
        system=QUERY_GEN_SYSTEM,
        messages=[{"role": "user", "content": batch_prompt}],
        timeout=30,
    )

    print(f"  Input tokens:  {message.usage.input_tokens}")
    print(f"  Output tokens: {message.usage.output_tokens}")
    print(f"  Stop reason:   {message.stop_reason}")

    response_text = message.content[0].text.strip()
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        response_text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        response_text = response_text.strip()

    data = json.loads(response_text)
    results_map = data.get("results", {})
    print(f"  Questions answered: {len(results_map)}")

    for qid, qdata in results_map.items():
        queries = qdata.get("queries", [])
        for q in queries:
            print(f"    [{qid}] {q.get('ik_query', '?')[:70]}")
            print(f"           doctype={q.get('doctype', '?')}, sort={q.get('sort', '?')}")

    assert len(results_map) >= 2, f"Expected >= 2 question results, got {len(results_map)}"


def test_3_relevance_filtering():
    print("  Model: claude-3-haiku-20240307")

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    case_summary = (
        "Patent appeal under Section 117A, Patents Act 1970. Huawei v. ACPD. "
        "Bombay High Court. Challenging refusal of patent for AKMA authentication "
        "in 5G/6G networks. Issues: novelty over D3, inventive step, Section 3(k)."
    )

    judgments = [
        {"tid": 195868937, "title": "Ab Initio Technology LLC v. ACPD, 2024:DHC:708",
         "headline": "Section 3(k) Patents Act — computer programme per se — technical effect test"},
        {"tid": 123456789, "title": "Agfa NV v. ACPD, 2023:DHC:4030",
         "headline": "Obviousness analysis — common general knowledge — Section 2(1)(ja)"},
        {"tid": 987654321, "title": "State of Maharashtra v. Union of India, 2020",
         "headline": "Criminal appeal — murder conviction — circumstantial evidence"},
        {"tid": 111222333, "title": "Lava International v. Ericsson, 2024:DHC:2698",
         "headline": "Patent validity — FRAND licensing — Section 3(k) — technical effect"},
    ]

    judgment_list = ""
    for idx, r in enumerate(judgments):
        judgment_list += f"\n[{idx+1}] TID={r['tid']} | {r['title']}\n    {r['headline']}\n"

    prompt = (
        "You are a legal research relevance assessor. Score each judgment's relevance.\n\n"
        f"CASE CONTEXT:\n{case_summary}\n\n"
        f"JUDGMENTS TO EVALUATE:{judgment_list}\n\n"
        "For EACH judgment, score relevance 0-10 with one-line reasoning.\n\n"
        "RESPOND WITH ONLY THIS JSON (no markdown):\n"
        '{"scores": [{"tid": <number>, "score": <0-10>, "reasoning": "one line"}]}'
    )

    message = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
        timeout=30,
    )

    print(f"  Input tokens:  {message.usage.input_tokens}")
    print(f"  Output tokens: {message.usage.output_tokens}")
    print(f"  Stop reason:   {message.stop_reason}")

    response_text = message.content[0].text.strip()
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        response_text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        response_text = response_text.strip()

    data = json.loads(response_text)
    scores = data.get("scores", [])
    print(f"  Judgments scored: {len(scores)}")

    for s in scores:
        marker = "RELEVANT" if s["score"] >= 6 else "IRRELEVANT"
        print(f"    TID {s['tid']}: {s['score']}/10 [{marker}] — {s['reasoning']}")

    assert len(scores) == 4, f"Expected 4 scores, got {len(scores)}"

    criminal = next((s for s in scores if s["tid"] == 987654321), None)
    if criminal and criminal["score"] < 6:
        print(f"  Sanity check PASS: Criminal case correctly scored low ({criminal['score']}/10)")
    elif criminal:
        print(f"  Sanity check WARNING: Criminal case scored {criminal['score']}/10 (expected < 6)")


def test_4_genome_extraction():
    print(f"  Model: {APIConfig.model()}")

    system_prompt = build_master_prompt()
    schema_summary = get_schema_summary()

    user_message = (
        f"## SCHEMA SUMMARY\n{schema_summary}\n\n"
        f"## JUDGMENT TEXT\n\n"
        f"Citation: Ab Initio Technology LLC v. ACPD, 2024:DHC:708\n\n"
        f"{SAMPLE_JUDGMENT_TEXT}"
    )

    client = anthropic.Anthropic(api_key=APIConfig.api_key())
    message = client.messages.create(
        model=APIConfig.model(),
        max_tokens=15000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        timeout=300,
    )

    print(f"  Input tokens:  {message.usage.input_tokens}")
    print(f"  Output tokens: {message.usage.output_tokens}")
    print(f"  Stop reason:   {message.stop_reason}")

    response_text = message.content[0].text
    cleaned = strip_markdown_fences(response_text)
    genome = json.loads(cleaned)

    dims = [
        ("dimension_1_visible", "Visible"),
        ("dimension_2_structural", "Structural"),
        ("dimension_3_invisible", "Invisible"),
        ("dimension_4_weaponizable", "Weaponizable"),
        ("dimension_5_synthesis", "Synthesis"),
        ("dimension_6_audit", "Audit"),
    ]

    all_present = True
    for key, label in dims:
        present = key in genome
        if not present:
            all_present = False
        print(f"    {label}: {'present' if present else 'MISSING'}")

    doc_id = genome.get("document_id", "?")
    print(f"  Document ID: {doc_id}")

    cert = genome.get("dimension_6_audit", {}).get("final_certification", {}).get("certification_level", "?")
    print(f"  Certification: {cert}")

    durability = genome.get("dimension_4_weaponizable", {}).get("vulnerability_map", {}).get("overall_durability_score", "?")
    print(f"  Durability: {durability}")

    assert all_present, "Not all 6 genome dimensions present"


def test_5_synthesis():
    print(f"  Model: {os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-6')}")

    from synthesis import synthesize_research

    sample_genome = {
        "tid": 195868937,
        "title": "Ab Initio Technology LLC v. ACPD, 2024:DHC:708",
        "relevance_score": 9,
        "relevance_reasoning": "Directly on Section 3(k) technical effect test",
        "genome": {
            "document_id": "Ab Initio v ACPD",
            "dimension_1_visible": {
                "ratio_decidendi": [
                    "A system enabling more efficient and faster output results in a technical effect not barred by Section 3(k)"
                ],
                "statutory_provisions": ["Section 3(k) Patents Act 1970", "Section 2(1)(j) Patents Act 1970"],
                "precedents_cited": []
            },
            "dimension_4_weaponizable": {
                "sword_potential": {"offensive_uses": ["Cite to argue AKMA integration produces technical effect"]},
                "shield_potential": {"defensive_uses": ["Counter Section 3(k) objection"]},
                "vulnerability_map": {"overall_durability_score": 8}
            },
            "dimension_5_synthesis": {
                "cheat_sheet": {"killer_paragraphs": ["Para 45: technical effect test for Section 3(k)"]}
            },
            "dimension_6_audit": {
                "final_certification": {"certification_level": "HIGH_CONFIDENCE"}
            }
        }
    }

    case_context = {
        "citation": "Huawei v. ACPD, Appeal 2026",
        "court": "Bombay High Court",
        "pleading_type": "PATENT_APPEAL",
        "client_name": "Huawei Technologies Co., Ltd.",
        "client_side": "APPELLANT",
        "opposite_party": "ACPD",
    }

    questions_data = {
        "categories": [
            {"category_name": "Jurisdictional", "questions": [
                {"question_id": "Q1", "question": "Whether appeal under Section 117A(2) is maintainable?",
                 "importance": "CRITICAL", "is_gate_question": True}
            ]},
            {"category_name": "Substantive", "questions": [
                {"question_id": "Q2", "question": "Whether D3 anticipates Claim 16?",
                 "importance": "CRITICAL", "is_gate_question": True},
                {"question_id": "Q3", "question": "Whether invention is excluded under Section 3(k)?",
                 "importance": "HIGH", "is_gate_question": False}
            ]}
        ]
    }

    memo, usage = synthesize_research(
        pleading_text=PLEADING_EXCERPT,
        case_context=case_context,
        genomes=[sample_genome],
        questions_data=questions_data,
    )

    print(f"  Input tokens:  {usage.get('input_tokens', '?')}")
    print(f"  Output tokens: {usage.get('output_tokens', '?')}")
    print(f"  Model used:    {usage.get('model', '?')}")

    expected_keys = [
        "memo_metadata", "executive_summary", "advocate_perspective",
        "opponent_perspective", "judicial_perspective", "issue_wise_analysis",
        "citation_matrix", "research_gaps", "action_items"
    ]

    all_present = True
    for key in expected_keys:
        present = key in memo
        if not present:
            all_present = False
        print(f"    {key}: {'present' if present else 'MISSING'}")

    strength = memo.get("overall_case_strength", "?")
    print(f"  Overall case strength: {strength}")

    issues = memo.get("issue_wise_analysis", [])
    print(f"  Issues analyzed: {len(issues)}")
    for iss in issues[:3]:
        print(f"    - {iss.get('issue', '?')[:60]} | outcome={iss.get('likely_outcome', '?')}")

    gaps = memo.get("research_gaps", [])
    print(f"  Research gaps: {len(gaps)}")
    for g in gaps[:2]:
        print(f"    - {g[:80]}")

    assert all_present, "Not all expected keys present in memo"


if __name__ == "__main__":
    test_num = None
    if len(sys.argv) > 1:
        test_num = int(sys.argv[1])

    print("=" * 70)
    print("CourtCraft.ai — Claude API Integration Test Suite")
    print("=" * 70)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)
    print(f"API Key: ...{api_key[-8:]}")
    print(f"Sonnet model: {APIConfig.model()}")

    tests = [
        ("1. Question Extraction (Sonnet 4)", test_1_question_extraction),
        ("2. Query Generation (Haiku)", test_2_query_generation),
        ("3. Relevance Filtering (Haiku)", test_3_relevance_filtering),
        ("4. Genome Extraction (Sonnet 4)", test_4_genome_extraction),
        ("5. Synthesis (Sonnet 4)", test_5_synthesis),
    ]

    if test_num:
        tests = [tests[test_num - 1]]

    for name, fn in tests:
        run_test(name, fn)

    print(f"\n\n{'='*70}")
    print("RESULTS SUMMARY")
    print(f"{'='*70}")

    total_time = 0
    passed = 0
    failed = 0
    for name, success, elapsed, error in results_log:
        status = PASS if success else FAIL
        print(f"  [{status}] {name} ({elapsed:.1f}s)")
        if error:
            print(f"         Error: {error[:120]}")
        total_time += elapsed
        if success:
            passed += 1
        else:
            failed += 1

    print(f"\n  Total: {passed} passed, {failed} failed, {total_time:.1f}s elapsed")
    print(f"{'='*70}")
