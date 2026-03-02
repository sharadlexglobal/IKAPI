import json
import logging
import os
import re
import time
import psycopg2
import psycopg2.extras
import anthropic

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

QUERY_EXPANSION_PROMPT = """You are an expert Indian legal researcher. Given a legal research question, extract structured search terms to find relevant judgment genomes in a database.

The database contains pre-analyzed Indian court judgments with these searchable fields:
- provisions_engaged: Sections, Articles, Rules cited (e.g., "Section 138 NI Act", "Article 226")
- ratio_decidendi: The core legal holding/principle
- sword_uses/shield_uses: How the judgment can be used offensively or defensively
- genome_summary: Overall summary of the judgment's legal significance
- taxonomy topics and categories

AVAILABLE TAXONOMY CATEGORIES AND TOPICS:
{taxonomy_list}

YOUR TASK: Extract search terms from the question below.

RESPOND WITH ONLY VALID JSON, NO MARKDOWN:
{{"statutory_terms": ["cheque dishonour", "negotiable instrument", ...], "synonyms": ["alternative phrasing 1", "related term", ...], "provisions": ["Section X of Act Y", ...], "legal_concepts": ["concept1", "concept2", ...], "taxonomy_ids": ["TOPIC_ID1", "CATEGORY_ID1", ...], "negative_keywords": ["term that indicates NOT relevant", ...]}}

RULES:
1. statutory_terms: 3-8 specific legal terms from statutes or legal doctrine that would appear in judgment text. Do NOT include generic terms like court, judgment, case, law, act, petition, order, appeal — only terms specific to the legal issue.
2. synonyms: 3-6 alternative phrasings or related terms that mean the same thing as the core issue. Example: if question mentions laches, also include delay, acquiescence. If question mentions quashing, also include setting aside, striking down.
3. provisions: Exact statutory provisions referenced or implied (Section, Article, Rule, Order numbers with Act name)
4. legal_concepts: 2-5 abstract legal principles involved (e.g., inherent jurisdiction, natural justice, res judicata)
5. taxonomy_ids: Pick from the available list above — only IDs that DIRECTLY match the legal issue in the question. Do NOT pick broad categories just because they vaguely relate. If no taxonomy ID clearly matches, return an empty list.
6. negative_keywords: 2-3 terms that would indicate a genome is about a DIFFERENT legal issue and NOT relevant. Example: if question is about cheque dishonour, a negative keyword might be motor accident or land acquisition.
7. Be broad enough to catch related judgments but specific enough to exclude noise. If the question is about a legal area NOT covered in the taxonomy list (e.g., patent law, environmental law), return empty taxonomy_ids — do not force-fit unrelated categories."""

RELEVANCE_FILTER_PROMPT = """You are an expert Indian legal researcher. Given a legal research question and a list of judgment genome summaries, determine which judgments are RELEVANT to answering the question.

RESEARCH QUESTION:
{question}

CANDIDATE JUDGMENTS:
{candidates}

For each judgment, first ANALYZE its relationship to the question, then assign a relevance score from 1-10:
- 9-10: Directly on point — addresses the SAME legal issue with an applicable holding, WHETHER it supports OR opposes the position in the question
- 7-8: Highly relevant — same legal area, discusses the core principle, a key exception, or an important procedural aspect
- 5-6: Useful background — related legal area, provides context, defines key terms, or establishes a procedural framework used in the main issue
- 3-4: Tangentially related — different legal issue but shares a procedural or statutory overlap
- 1-2: Not relevant to the question

CRITICAL FILTERING RULES:
1. Contrary authority (judgments that OPPOSE the proposition in the question) should score 8-10 if they address the same legal issue. A practicing lawyer MUST know about contrary holdings.
2. A judgment that merely MENTIONS a word from the question is NOT relevant. The judgment must actually ADDRESS the legal issue in the question. For example, if the question is about patent law, a cheque dishonour case that happens to mention the word "drug" is score 1-2, NOT 5-6.
3. Be STRICT. If the judgment discusses a fundamentally different area of law than the question, score it 1-2 regardless of incidental word overlaps.
4. When relevance is otherwise equal, give slight preference to Supreme Court judgments over High Court, and High Court over Tribunals/lower courts.

RESPOND WITH ONLY VALID JSON, NO MARKDOWN:
{{"scored": [{{"tid": 12345, "analysis": "2-3 sentences: what legal issue this judgment addresses, how it relates to the research question, and whether it supports or opposes the position", "score": 8}}, ...]}}

Only include judgments with score >= 6. Exclude irrelevant ones entirely."""

REPORT_GENERATION_PROMPT = """You are a Senior Advocate with 40+ years of practice before the Supreme Court of India. You are writing a legal research report based on pre-analyzed judgment genomes.

CRITICAL RULES:
1. ONLY cite case titles, paragraph numbers, and holdings that are EXPLICITLY present in the genome data provided
2. DO NOT fabricate any citation, paragraph number, or holding
3. Use proper Indian legal citation format
4. If a genome has sword_uses or shield_uses, incorporate them into practical application
5. If a genome has vulnerability_map, note weaknesses where relevant
6. Structure the report for a practicing advocate who needs actionable research
7. Organize judgments by court hierarchy — Supreme Court of India holdings are BINDING precedent. High Court holdings are binding within that state and PERSUASIVE in other states. Tribunal/lower court holdings are persuasive only. Label each judgment accordingly.
8. If an older judgment exists alongside a newer one on the same legal point, note the temporal relationship. Later judgments may have distinguished, explained, or overruled earlier ones — check the genome's precedent_registry for this information.

RESEARCH QUESTION:
{question}

JUDGMENT GENOME DATA:
{genome_data}

Write a comprehensive legal research report with these sections:

1. EXECUTIVE SUMMARY (3-5 sentences answering the research question based on the genomes)

2. KEY LEGAL PRINCIPLES (numbered list — each principle must cite the exact case title and paragraph number from the genome data. Note whether the source is a Supreme Court or High Court judgment.)

3. SUPPORTING JUDGMENTS (for each relevant judgment:
   - Case title and citation
   - Court, year, and authority status (BINDING / PERSUASIVE)
   - Ratio decidendi (from genome)
   - Key paragraphs referenced
   - How it supports the research question)

4. CONTRARY / DISTINGUISHABLE POSITIONS — THIS SECTION IS CRITICAL. If ANY genome data contains holdings, ratio decidendi, or vulnerability_map entries that oppose or weaken the legal position in the question, they MUST appear here. Do not omit contrary authority. Include:
   - Any judgments that take an opposing view
   - Any vulnerabilities noted in genome vulnerability_map
   - Any distinguishing factors that could limit applicability
   If no contrary authority exists in the provided genomes, state so explicitly.

5. PRACTICAL APPLICATION (specific advice on how to use these judgments — cite sword_uses and shield_uses from genomes where available)

6. STRENGTH ASSESSMENT (on a scale of STRONG / MODERATE / WEAK, how well-supported is the legal position based on available genomes, with reasoning. Factor in: number of Supreme Court authorities, presence or absence of contrary holdings, recency of judgments.)

Write in formal legal English suitable for court submissions."""


def _get_db():
    return psycopg2.connect(DATABASE_URL)


def _get_taxonomy_list():
    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, name FROM taxonomy_categories ORDER BY id")
            categories = cur.fetchall()
            cur.execute("SELECT id, name, category_id FROM taxonomy_topics ORDER BY id")
            topics = cur.fetchall()
        lines = ["CATEGORIES:"]
        for c in categories:
            lines.append(f"  {c['id']}: {c['name']}")
        lines.append("\nTOPICS:")
        for t in topics:
            lines.append(f"  {t['id']}: {t['name']} (category: {t['category_id']})")
        return "\n".join(lines)
    finally:
        conn.close()


def _call_haiku(system_prompt, user_message, max_retries=1):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    last_error = None
    for attempt in range(max_retries + 1):
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=4000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            timeout=60,
        )
        raw = message.content[0].text.strip()
        raw = raw.replace('\u201c', '"').replace('\u201d', '"')
        raw = raw.replace('\u2018', "'").replace('\u2019', "'")
        usage = {"input_tokens": message.usage.input_tokens, "output_tokens": message.usage.output_tokens}
        try:
            parsed = json.loads(raw)
            return parsed, usage
        except json.JSONDecodeError:
            start = raw.find('{')
            end = raw.rfind('}')
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(raw[start:end + 1])
                    return parsed, usage
                except json.JSONDecodeError:
                    pass
            last_error = f"JSON parse failed on attempt {attempt + 1}"
            if attempt < max_retries:
                logger.warning(f"[genome-research] Haiku JSON parse failed (attempt {attempt + 1}), retrying...")
                continue
    raise ValueError(f"Failed to parse AI response as valid JSON after {max_retries + 1} attempts. Please try again.")


def _call_sonnet(system_prompt, user_message, max_tokens=8000):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        timeout=120,
    )
    text = message.content[0].text.strip()
    usage = {"input_tokens": message.usage.input_tokens, "output_tokens": message.usage.output_tokens}
    return text, usage


def expand_query(question):
    t0 = time.time()
    taxonomy_list = _get_taxonomy_list()
    prompt = QUERY_EXPANSION_PROMPT.format(taxonomy_list=taxonomy_list)
    parsed, usage = _call_haiku(prompt, question)
    elapsed_ms = int((time.time() - t0) * 1000)

    statutory_terms = parsed.get("statutory_terms", [])
    synonyms = parsed.get("synonyms", [])
    negative_keywords = parsed.get("negative_keywords", [])
    keywords_combined = list(set(statutory_terms + synonyms + parsed.get("keywords", [])))

    logger.info(f"[genome-research] Query expansion: {len(statutory_terms)} statutory_terms, "
                f"{len(synonyms)} synonyms, "
                f"{len(parsed.get('provisions', []))} provisions, "
                f"{len(parsed.get('legal_concepts', []))} concepts, "
                f"{len(parsed.get('taxonomy_ids', []))} taxonomy matches, "
                f"{len(negative_keywords)} negative_keywords in {elapsed_ms}ms")
    return {
        "keywords": keywords_combined,
        "statutory_terms": statutory_terms,
        "synonyms": synonyms,
        "negative_keywords": negative_keywords,
        "provisions": parsed.get("provisions", []),
        "legal_concepts": parsed.get("legal_concepts", []),
        "taxonomy_ids": parsed.get("taxonomy_ids", []),
        "timing_ms": elapsed_ms,
        "usage": usage,
    }


def discover_relevant_genomes(expanded_query):
    t0 = time.time()
    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT g.id, g.tid, g.genome_json, g.schema_version,
                       g.certification_level, g.overall_durability_score,
                       j.title, j.court_source, j.publish_date, j.num_cited_by
                FROM judgment_genomes g
                LEFT JOIN judgments j ON g.tid = j.tid
            """)
            all_genomes = cur.fetchall()

            cur.execute("""
                SELECT gt.genome_tid, gt.topic_id, gt.confidence
                FROM genome_topics gt
            """)
            topic_links = {}
            for row in cur.fetchall():
                topic_links.setdefault(row['genome_tid'], []).append(row['topic_id'])

            cur.execute("""
                SELECT gc.genome_tid, gc.category_id
                FROM genome_categories gc
            """)
            category_links = {}
            for row in cur.fetchall():
                category_links.setdefault(row['genome_tid'], []).append(row['category_id'])

        scored_genomes = []
        keywords = expanded_query.get("keywords", [])
        provisions = expanded_query.get("provisions", [])
        legal_concepts = expanded_query.get("legal_concepts", [])
        taxonomy_ids = expanded_query.get("taxonomy_ids", [])
        negative_keywords = expanded_query.get("negative_keywords", [])

        for genome in all_genomes:
            score = 0
            signals = []
            gid = genome['id']
            gj = genome['genome_json']
            if isinstance(gj, str):
                gj = json.loads(gj)
            gj_text = json.dumps(gj).lower()

            negative_hit = False
            for nk in negative_keywords:
                if nk.lower() in gj_text:
                    negative_hit = True
                    break

            genome_topic_ids = topic_links.get(genome['tid'], [])
            genome_cat_ids = category_links.get(genome['tid'], [])
            for tid in taxonomy_ids:
                if tid in genome_topic_ids or tid in genome_cat_ids:
                    score += 3
                    signals.append(f"taxonomy:{tid}")

            d1 = gj.get("dimension_1_visible", {})
            provisions_engaged = d1.get("provisions_engaged", [])
            prov_text = json.dumps(provisions_engaged).lower() if provisions_engaged else ""
            for prov in provisions:
                prov_lower = prov.lower()
                prov_parts = re.findall(r'section\s+\d+[a-z]*|article\s+\d+[a-z]*|rule\s+\d+|order\s+\w+', prov_lower)
                for part in prov_parts:
                    if part in prov_text:
                        score += 3
                        signals.append(f"provision:{part}")
                        break
                else:
                    if prov_lower in prov_text:
                        score += 3
                        signals.append(f"provision:{prov_lower}")

            ratio = d1.get("ratio_decidendi", {})
            ratio_text = json.dumps(ratio).lower() if ratio else ""
            d4 = gj.get("dimension_4_weaponizable", {})
            d4_text = json.dumps(d4).lower() if d4 else ""

            for concept in legal_concepts:
                concept_lower = concept.lower()
                if concept_lower in ratio_text:
                    score += 2
                    signals.append(f"ratio:{concept}")
                elif concept_lower in d4_text:
                    score += 2
                    signals.append(f"weapon:{concept}")

            keyword_score = 0
            for kw in keywords:
                if kw.lower() in gj_text:
                    keyword_score += 1
                    signals.append(f"keyword:{kw}")
            score += min(keyword_score, 3)

            if negative_hit and score > 0:
                score = max(1, score - 2)
                signals.append("negative_keyword_penalty")

            if score > 0:
                d5 = gj.get("dimension_5_synthesis", {})
                genome_summary = d5.get("genome_summary", {})
                summary_text = ""
                if isinstance(genome_summary, dict):
                    summary_text = genome_summary.get("text", "") or json.dumps(genome_summary)
                elif isinstance(genome_summary, str):
                    summary_text = genome_summary

                ratio_text_short = ""
                if isinstance(ratio, list):
                    propositions = []
                    for r_item in ratio:
                        if isinstance(r_item, dict):
                            prop = r_item.get("proposition", "") or r_item.get("label", "")
                            if prop:
                                propositions.append(prop)
                    ratio_text_short = " | ".join(propositions)[:500] if propositions else json.dumps(ratio)[:500]
                elif isinstance(ratio, dict):
                    ratio_text_short = ratio.get("proposition", "") or ratio.get("primary_ratio", "") or ratio.get("text", "") or json.dumps(ratio)[:500]
                elif isinstance(ratio, str):
                    ratio_text_short = ratio[:500]

                provisions_short = ""
                if provisions_engaged:
                    if isinstance(provisions_engaged, list):
                        prov_names = []
                        for pe in provisions_engaged:
                            if isinstance(pe, dict):
                                prov_names.append(pe.get("provision", "") or pe.get("name", "") or str(pe))
                            elif isinstance(pe, str):
                                prov_names.append(pe)
                        provisions_short = "; ".join(prov_names)[:500]
                    else:
                        provisions_short = json.dumps(provisions_engaged)[:500]

                scored_genomes.append({
                    "id": gid,
                    "tid": genome['tid'],
                    "title": genome.get('title', ''),
                    "court": genome.get('court_source', ''),
                    "date": str(genome.get('publish_date', '')),
                    "cited_by": genome.get('num_cited_by', 0),
                    "durability": genome.get('overall_durability_score', 0),
                    "certification": genome.get('certification_level', ''),
                    "score": score,
                    "signals": signals,
                    "summary": summary_text[:1000],
                    "ratio": ratio_text_short[:500],
                    "provisions_engaged": provisions_short,
                })

        scored_genomes.sort(key=lambda x: x['score'], reverse=True)
        top_candidates = scored_genomes[:20]

        elapsed_ms = int((time.time() - t0) * 1000)
        logger.info(f"[genome-research] Discovery: {len(all_genomes)} total genomes, "
                    f"{len(scored_genomes)} with matches, top {len(top_candidates)} candidates in {elapsed_ms}ms")
        return {
            "total_searched": len(all_genomes),
            "candidates": top_candidates,
            "timing_ms": elapsed_ms,
        }
    finally:
        conn.close()


def filter_relevant(question, candidates, min_score=6):
    if not candidates:
        return {"relevant": [], "timing_ms": 0, "usage": {"input_tokens": 0, "output_tokens": 0}}

    t0 = time.time()
    candidate_text = ""
    for i, c in enumerate(candidates):
        prov_line = f"Provisions: {c.get('provisions_engaged', 'N/A')}\n" if c.get('provisions_engaged') else ""
        candidate_text += (
            f"\n--- Judgment {i + 1} ---\n"
            f"TID: {c['tid']}\n"
            f"Title: {c['title']}\n"
            f"Court: {c['court']}\n"
            f"{prov_line}"
            f"Ratio: {c['ratio']}\n"
            f"Summary: {c['summary']}\n"
            f"DB Match Score: {c['score']} (signals: {', '.join(c['signals'][:5])})\n"
        )

    prompt = RELEVANCE_FILTER_PROMPT.format(question=question, candidates=candidate_text)
    parsed, usage = _call_haiku(prompt, "Analyze and score the candidate judgments above.")
    elapsed_ms = int((time.time() - t0) * 1000)

    scored = parsed.get("scored", [])
    relevant_tids = {}
    for item in scored:
        if item.get("score", 0) >= min_score:
            tid_val = item.get("tid")
            try:
                tid_val = int(tid_val)
            except (ValueError, TypeError):
                continue
            reason = item.get("analysis", "") or item.get("reason", "")
            relevant_tids[tid_val] = {"score": item["score"], "reason": reason}

    relevant = []
    for c in candidates:
        c_tid = int(c['tid']) if c.get('tid') is not None else None
        if c_tid in relevant_tids:
            c['relevance_score'] = relevant_tids[c_tid]['score']
            c['relevance_reason'] = relevant_tids[c_tid]['reason']
            relevant.append(c)

    relevant.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)

    logger.info(f"[genome-research] Filter: {len(candidates)} candidates -> {len(relevant)} relevant in {elapsed_ms}ms")
    return {
        "relevant": relevant,
        "timing_ms": elapsed_ms,
        "usage": usage,
    }


def _extract_genome_data_for_report(relevant_genomes):
    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            tids = [g['tid'] for g in relevant_genomes]
            if not tids:
                return ""

            placeholders = ','.join(['%s'] * len(tids))
            cur.execute(f"""
                SELECT g.tid, g.genome_json, j.title, j.court_source, j.publish_date
                FROM judgment_genomes g
                LEFT JOIN judgments j ON g.tid = j.tid
                WHERE g.tid IN ({placeholders})
            """, tids)
            rows = cur.fetchall()

        tid_order = {tid: i for i, tid in enumerate(tids)}
        rows.sort(key=lambda r: tid_order.get(r['tid'], 999))

        genome_data_parts = []
        for row in rows:
            gj = row['genome_json']
            if isinstance(gj, str):
                gj = json.loads(gj)

            d1 = gj.get("dimension_1_visible", {})
            d4 = gj.get("dimension_4_weaponizable", {})
            d5 = gj.get("dimension_5_synthesis", {})

            case_identity = d1.get("case_identity", {})
            ratio = d1.get("ratio_decidendi", {})
            provisions = d1.get("provisions_engaged", [])
            precedents = d1.get("precedent_registry", {})
            operative_order = d1.get("operative_order", {})

            sword = d4.get("sword_uses", [])
            shield = d4.get("shield_uses", [])
            vulnerability = d4.get("vulnerability_map", {})
            distinguishing = d4.get("distinguishing_playbook", {})

            cheat_sheet = d5.get("practitioners_cheat_sheet", {})
            genome_summary = d5.get("genome_summary", {})
            killer_paras = d5.get("extraction_confidence", {})

            def _safe_json(obj, max_len=2000):
                s = json.dumps(obj, indent=2, default=str)
                if len(s) <= max_len:
                    return s
                s = json.dumps(obj, default=str)
                if len(s) <= max_len:
                    return s
                return s[:max_len - 3] + "..."

            part = f"""
=== JUDGMENT: {row.get('title', 'Unknown')} ===
TID: {row['tid']}
Court: {row.get('court_source', 'Unknown')}
Date: {row.get('publish_date', 'Unknown')}

CASE IDENTITY:
{_safe_json(case_identity, 1500)}

RATIO DECIDENDI:
{_safe_json(ratio, 2000)}

PROVISIONS ENGAGED:
{_safe_json(provisions, 1000)}

OPERATIVE ORDER:
{_safe_json(operative_order, 500)}

SWORD USES (offensive):
{_safe_json(sword, 1500)}

SHIELD USES (defensive):
{_safe_json(shield, 1500)}

VULNERABILITY MAP:
{_safe_json(vulnerability, 1000)}

DISTINGUISHING PLAYBOOK:
{_safe_json(distinguishing, 1000)}

PRECEDENT REGISTRY:
{_safe_json(precedents, 1500)}

PRACTITIONERS CHEAT SHEET:
{_safe_json(cheat_sheet, 1500)}

GENOME SUMMARY:
{_safe_json(genome_summary, 1000)}
"""
            genome_data_parts.append(part)

        return "\n\n".join(genome_data_parts)
    finally:
        conn.close()


def generate_report(question, relevant_genomes):
    if not relevant_genomes:
        return {
            "report_text": "No relevant genomes found in the database for this research question. Please save genomes for relevant judgments first.",
            "timing_ms": 0,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }

    t0 = time.time()
    genome_data = _extract_genome_data_for_report(relevant_genomes)

    prompt = REPORT_GENERATION_PROMPT.format(question=question, genome_data=genome_data)
    report_text, usage = _call_sonnet(
        "You are a legal research report writer. Follow the instructions precisely.",
        prompt,
        max_tokens=8000,
    )
    elapsed_ms = int((time.time() - t0) * 1000)

    logger.info(f"[genome-research] Report generated: {len(report_text)} chars, "
                f"{usage['input_tokens']} in / {usage['output_tokens']} out in {elapsed_ms}ms")
    return {
        "report_text": report_text,
        "timing_ms": elapsed_ms,
        "usage": usage,
    }


def run_genome_research(question, max_genomes=15):
    t_start = time.time()
    total_usage = {"input_tokens": 0, "output_tokens": 0}
    timings = {}

    try:
        expanded = expand_query(question)
        timings["expand_ms"] = expanded["timing_ms"]
        total_usage["input_tokens"] += expanded["usage"]["input_tokens"]
        total_usage["output_tokens"] += expanded["usage"]["output_tokens"]
        expanded_clean = {k: v for k, v in expanded.items() if k not in ("usage", "timing_ms")}

        discovery = discover_relevant_genomes(expanded)
        timings["discover_ms"] = discovery["timing_ms"]

        candidates = discovery["candidates"]
        if not candidates:
            return {
                "success": True,
                "report": {
                    "report_text": "No matching genomes found in the database for this research question. The database currently has genomes for specific legal topics. Please save genomes for judgments relevant to your question first.",
                },
                "discovery": {
                    "total_genomes_searched": discovery["total_searched"],
                    "candidates_found": 0,
                    "relevant_found": 0,
                    "expanded_query": expanded_clean,
                },
                "relevant_judgments": [],
                "timing": timings,
                "token_usage": total_usage,
                "total_time_seconds": round(time.time() - t_start, 2),
            }

        filtered = filter_relevant(question, candidates)
        timings["filter_ms"] = filtered["timing_ms"]
        total_usage["input_tokens"] += filtered["usage"]["input_tokens"]
        total_usage["output_tokens"] += filtered["usage"]["output_tokens"]

        relevant = filtered["relevant"][:max_genomes]

        if not relevant:
            return {
                "success": True,
                "report": {
                    "report_text": f"Found {len(candidates)} candidate genomes but none were sufficiently relevant to your specific question. The database has genomes on related topics but they don't directly address your query. Consider saving genomes for more targeted judgments.",
                },
                "discovery": {
                    "total_genomes_searched": discovery["total_searched"],
                    "candidates_found": len(candidates),
                    "relevant_found": 0,
                    "expanded_query": expanded_clean,
                },
                "relevant_judgments": [],
                "timing": timings,
                "token_usage": total_usage,
                "total_time_seconds": round(time.time() - t_start, 2),
            }

        report_result = generate_report(question, relevant)
        timings["generate_ms"] = report_result["timing_ms"]
        total_usage["input_tokens"] += report_result["usage"]["input_tokens"]
        total_usage["output_tokens"] += report_result["usage"]["output_tokens"]

        total_seconds = round(time.time() - t_start, 2)
        timings["total_ms"] = int(total_seconds * 1000)

        return {
            "success": True,
            "report": {
                "report_text": report_result["report_text"],
            },
            "discovery": {
                "total_genomes_searched": discovery["total_searched"],
                "candidates_found": len(candidates),
                "relevant_found": len(relevant),
                "expanded_query": expanded_clean,
            },
            "relevant_judgments": [
                {
                    "tid": g["tid"],
                    "title": g["title"],
                    "court": g["court"],
                    "date": g["date"],
                    "cited_by": g["cited_by"],
                    "durability": g["durability"],
                    "relevance_score": g.get("relevance_score", 0),
                    "relevance_reason": g.get("relevance_reason", ""),
                    "signals": g["signals"],
                }
                for g in relevant
            ],
            "timing": timings,
            "token_usage": total_usage,
            "total_time_seconds": total_seconds,
        }

    except Exception as e:
        logger.error(f"[genome-research] Error: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timing": timings,
            "token_usage": total_usage,
            "total_time_seconds": round(time.time() - t_start, 2),
        }
