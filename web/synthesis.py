"""
Dual-Perspective Research Synthesis — produces the final research memo.
Uses Claude Sonnet 4 for premium-quality analysis.
"""
import json
import logging
import os
import anthropic

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = """You are a Senior Advocate with 60+ years of practice before the Supreme Court of India, all High Courts, and every Tribunal. You have been provided with:
1. A litigation pleading (the client's case)
2. Structured genome extractions from relevant judgments (each genome has 6 dimensions: Visible, Structural, Invisible, Weaponizable, Synthesis, Audit)
3. The original research questions extracted from the pleading

Your task: Produce a comprehensive RESEARCH MEMO that will serve as the foundation for courtroom preparation.

YOU MUST ANALYZE FROM THREE PERSPECTIVES:
1. ADVOCATE PERSPECTIVE: How to use these judgments to WIN the case
2. OPPONENT PERSPECTIVE: How the opposing side will use these same (or other) judgments AGAINST the client
3. JUDICIAL PERSPECTIVE: What the judge will focus on, what questions they'll ask first

CRITICAL RULES:
1. Every judgment citation MUST reference the specific tid number
2. When recommending a judgment, explain WHY it helps — reference the genome's ratio decidendi, killer paragraph, or cheat sheet
3. When warning about a dangerous judgment, explain the COUNTER-STRATEGY — reference the genome's vulnerability map and distinguishing points
4. Organize analysis ISSUE-WISE, not judgment-wise
5. Flag GATE QUESTIONS prominently — these are make-or-break issues
6. Be brutally honest about weaknesses in the client's case
7. Suggest specific action items the advocate should take BEFORE the hearing

OUTPUT FORMAT: Respond with ONLY valid JSON matching the schema below. No markdown fences, no preamble."""


SYNTHESIS_SCHEMA = """{
  "memo_metadata": {
    "case": "string",
    "court": "string",
    "pleading_type": "string",
    "research_date": "YYYY-MM-DD",
    "judgments_analyzed": number,
    "genomes_used": number
  },
  "executive_summary": "3-4 paragraph overview of research findings and overall case assessment",
  "overall_case_strength": "STRONG / MODERATE / WEAK / CRITICAL_WEAKNESS",
  "advocate_perspective": {
    "strongest_arguments": [
      {
        "argument": "string",
        "supporting_judgments": [{"tid": number, "case_name": "string", "why_helpful": "string", "killer_paragraph": "string or null", "durability_score": number}],
        "confidence": "HIGH / MEDIUM / LOW"
      }
    ],
    "recommended_citation_strategy": "string",
    "procedural_strategy": "string"
  },
  "opponent_perspective": {
    "likely_counter_arguments": [
      {
        "argument": "string",
        "dangerous_judgments": [{"tid": number, "case_name": "string", "how_opponent_will_use": "string", "counter_strategy": "string", "distinguishing_points": ["string"]}],
        "severity": "HIGH / MEDIUM / LOW"
      }
    ],
    "weakest_points_in_pleading": ["string"],
    "what_judge_will_question": ["string"]
  },
  "judicial_perspective": {
    "likely_first_questions": ["string"],
    "jurisdictional_concerns": ["string"],
    "precedent_conflicts": ["string"],
    "what_will_persuade_bench": "string"
  },
  "issue_wise_analysis": [
    {
      "issue": "string",
      "gate_question": boolean,
      "for_petitioner": {"judgments": [{"tid": number, "case_name": "string", "how_to_use": "string"}], "argument_chain": "string"},
      "for_respondent": {"judgments": [{"tid": number, "case_name": "string", "how_to_use": "string"}], "argument_chain": "string"},
      "likely_outcome": "FAVOURABLE / UNCERTAIN / UNFAVOURABLE",
      "risk_level": "LOW / MEDIUM / HIGH / CRITICAL"
    }
  ],
  "citation_matrix": {
    "must_cite": [{"tid": number, "case_name": "string", "reason": "string"}],
    "good_to_cite": [{"tid": number, "case_name": "string", "reason": "string"}],
    "cite_with_caution": [{"tid": number, "case_name": "string", "risk": "string"}],
    "opponent_will_cite": [{"tid": number, "case_name": "string", "counter": "string"}]
  },
  "research_gaps": ["string - areas where no strong authority was found"],
  "action_items": ["string - specific things the advocate should do before hearing"]
}"""


def synthesize_research(pleading_text, case_context, genomes, questions_data=None):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    genome_summaries = _prepare_genome_summaries(genomes)

    questions_summary = ""
    if questions_data:
        questions_summary = _prepare_questions_summary(questions_data)

    case_header = _format_case_context(case_context)

    pleading_excerpt = pleading_text[:8000]
    if len(pleading_text) > 8000:
        pleading_excerpt += "\n\n[... truncated for synthesis ...]"

    user_message = f"""## RESEARCH MEMO SCHEMA
{SYNTHESIS_SCHEMA}

## CASE CONTEXT
{case_header}

## PLEADING (Excerpt)
{pleading_excerpt}

{questions_summary}

## JUDGMENT GENOMES ({len(genomes)} judgments analyzed)
{genome_summaries}

Generate the complete research memo now. Respond with ONLY valid JSON."""

    client = anthropic.Anthropic(api_key=api_key)
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    message = client.messages.create(
        model=model,
        max_tokens=30000,
        system=SYNTHESIS_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        timeout=600,
    )

    response_text = message.content[0].text.strip()
    if response_text.startswith("```"):
        response_text = response_text.strip("`").strip()
        if response_text.startswith("json"):
            response_text = response_text[4:].strip()

    memo = json.loads(response_text)
    usage = {}
    if hasattr(message, "usage"):
        usage = {"input_tokens": message.usage.input_tokens, "output_tokens": message.usage.output_tokens, "model": model}
    return memo, usage


def _prepare_genome_summaries(genomes):
    parts = []
    for g in genomes:
        tid = g["tid"]
        title = g.get("title", "Untitled")
        genome = g["genome"]
        rel_score = g.get("relevance_score", 0)
        rel_reason = g.get("relevance_reasoning", "")

        summary = f"\n### TID={tid} | {title} (Relevance: {rel_score}/10 — {rel_reason})\n"

        try:
            d1 = genome.get("dimension_1_visible", {})
            case_id = d1.get("case_identity", {})
            summary += f"- Case: {case_id.get('case_name', 'N/A')}\n"
            summary += f"- Court: {case_id.get('court_type', 'N/A')}\n"

            ratios = d1.get("ratio_decidendi", [])
            if ratios:
                for r in ratios[:3]:
                    if isinstance(r, dict):
                        summary += f"- RATIO: {r.get('label', 'N/A')} — {r.get('proposition', 'N/A')}\n"

            d4 = genome.get("dimension_4_weaponizable", {})
            sword = d4.get("sword_shield", {})
            sword_uses = sword.get("sword_uses", [])
            if sword_uses:
                for s in sword_uses[:2]:
                    if isinstance(s, dict):
                        summary += f"- SWORD USE: {s.get('scenario', 'N/A')}\n"

            shield_uses = sword.get("shield_uses", [])
            if shield_uses:
                for s in shield_uses[:2]:
                    if isinstance(s, dict):
                        summary += f"- SHIELD USE: {s.get('scenario', 'N/A')}\n"

            vuln = d4.get("vulnerability_map", {})
            durability = vuln.get("overall_durability_score", "N/A")
            summary += f"- DURABILITY: {durability}/10\n"

            attack_vectors = vuln.get("attack_vectors", [])
            if attack_vectors:
                for av in attack_vectors[:2]:
                    if isinstance(av, dict):
                        summary += f"- VULNERABILITY: {av.get('weak_point', 'N/A')}\n"

            d5 = genome.get("dimension_5_synthesis", {})
            cheat = d5.get("practitioners_cheat_sheet", {})
            if cheat:
                cite_when = cheat.get("cite_when", [])
                if cite_when:
                    summary += f"- CITE WHEN: {'; '.join(cite_when[:2])}\n"
                dont_cite = cheat.get("do_not_cite_when", [])
                if dont_cite:
                    summary += f"- DO NOT CITE WHEN: {'; '.join(dont_cite[:2])}\n"
                killer = cheat.get("killer_paragraph", "")
                if killer:
                    summary += f"- KILLER PARAGRAPH: {killer[:200]}\n"

        except Exception as e:
            summary += f"- [Error extracting genome summary: {e}]\n"

        parts.append(summary)

    return "\n".join(parts)


def _prepare_questions_summary(q_data):
    summary = "\n## KEY RESEARCH QUESTIONS\n"

    dt = q_data.get("decision_tree", {})
    gates = dt.get("gate_questions", [])
    if gates:
        summary += "\n### GATE QUESTIONS (Make-or-Break):\n"
        for g in gates[:5]:
            summary += f"- [{g.get('gate_question_id', '')}] {g.get('question_text', '')}\n"

    ext_summary = q_data.get("extraction_summary", {})
    if ext_summary.get("what_judge_will_ask_first"):
        summary += f"\n### WHAT JUDGE WILL ASK FIRST:\n{ext_summary['what_judge_will_ask_first']}\n"
    if ext_summary.get("biggest_vulnerability"):
        summary += f"\n### BIGGEST VULNERABILITY:\n{ext_summary['biggest_vulnerability']}\n"

    return summary


def _format_case_context(ctx):
    parts = []
    if ctx.get("citation"):
        parts.append(f"Case: {ctx['citation']}")
    if ctx.get("court"):
        parts.append(f"Court: {ctx['court']}")
    if ctx.get("pleading_type"):
        parts.append(f"Pleading Type: {ctx['pleading_type']}")
    if ctx.get("client_name"):
        parts.append(f"Client: {ctx['client_name']} ({ctx.get('client_side', 'N/A')})")
    if ctx.get("opposite_party"):
        parts.append(f"Opposite Party: {ctx['opposite_party']}")
    reliefs = ctx.get("reliefs_sought", [])
    if reliefs and isinstance(reliefs, list):
        parts.append(f"Reliefs Sought: {'; '.join(reliefs[:5])}")
    return "\n".join(parts)
