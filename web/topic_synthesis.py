import json
import logging
import os
import anthropic

logger = logging.getLogger(__name__)

TOPIC_SYNTHESIS_SYSTEM = """You are a Senior Legal Researcher with 60+ years of experience across all Indian courts. You have been provided with structured genome extractions from multiple judgments on the SAME legal topic.

Your task: Produce a comprehensive TOPIC SYNTHESIS that maps the complete legal landscape on this topic.

ANALYSIS REQUIREMENTS:
1. EVOLUTION TIMELINE: Trace how the law on this topic has developed through the judgments provided. Identify pivotal shifts.
2. CURRENT LEGAL POSITION: What is the settled law TODAY based on these judgments?
3. SETTLED PROPOSITIONS: Which legal propositions are consistently upheld across multiple judgments? Rate confidence.
4. OPEN QUESTIONS: Where do judgments diverge? What remains unsettled?
5. KILLER ARGUMENTS: What is the strongest argument a petitioner can make? What about the respondent?
6. PRACTICE ADVISORY: Practical advice for a lawyer handling a case on this topic.

CRITICAL RULES:
1. Every reference MUST include the TID number
2. Base analysis ONLY on the genome data provided — do not hallucinate cases
3. Be specific about which judgment supports which proposition
4. Flag any contradictions between judgments honestly
5. The evolution timeline should use actual dates/years from the judgments where available

OUTPUT: Respond with ONLY valid JSON matching the schema below. No markdown fences."""

TOPIC_SYNTHESIS_SCHEMA = """{
  "topic_name": "string",
  "evolution_timeline": [
    {"year_range": "string", "development": "string", "key_case_tid": number}
  ],
  "current_legal_position": "string (2-3 paragraphs summarizing the current state of law)",
  "settled_propositions": [
    {
      "proposition": "string",
      "supporting_tids": [number],
      "confidence": "HIGH / MEDIUM / LOW"
    }
  ],
  "open_questions": [
    {
      "question": "string",
      "competing_views": [
        {"view": "string", "supporting_tids": [number]}
      ]
    }
  ],
  "killer_argument": {
    "for_petitioner": "string",
    "for_respondent": "string",
    "strongest_case_tid": number
  },
  "practice_advisory": "string (practical advice for advocates)",
  "strength_assessment": "STRONG / MODERATE / WEAK / DEVELOPING"
}"""


def synthesize_topic(topic_id, force=False):
    from db import get_topic_genomes_with_json, get_topic_synthesis, save_topic_synthesis

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    genomes = get_topic_genomes_with_json(topic_id)
    if not genomes:
        raise ValueError(f"No genomes found for topic {topic_id}")

    if not force:
        cached = get_topic_synthesis(topic_id)
        if cached and cached.get("genome_count") == len(genomes):
            return cached["synthesis_json"], {"cached": True}

    genome_summaries = _prepare_topic_genome_summaries(genomes)

    user_message = f"""## TOPIC SYNTHESIS SCHEMA
{TOPIC_SYNTHESIS_SCHEMA}

## GENOMES FOR THIS TOPIC ({len(genomes)} judgments)
{genome_summaries}

Generate the complete topic synthesis now. Respond with ONLY valid JSON."""

    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=model,
        max_tokens=16000,
        system=TOPIC_SYNTHESIS_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
        timeout=300,
    )

    response_text = message.content[0].text.strip()
    if response_text.startswith("```"):
        response_text = response_text.strip("`").strip()
        if response_text.startswith("json"):
            response_text = response_text[4:].strip()

    synthesis = json.loads(response_text)

    usage = {}
    if hasattr(message, "usage"):
        usage = {
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
            "model": model, "cached": False,
        }

    save_topic_synthesis(topic_id, synthesis, model, len(genomes))
    return synthesis, usage


def _prepare_topic_genome_summaries(genomes):
    parts = []
    for g in genomes:
        tid = g["tid"]
        title = g.get("title", "Untitled")
        genome = g["genome_json"]
        durability = g.get("overall_durability_score", "N/A")

        summary = f"\n### TID={tid} | {title} | Durability: {durability}/10\n"

        try:
            d1 = genome.get("dimension_1_visible", {})
            case_id = d1.get("case_identity", {})
            summary += f"- Court: {case_id.get('court_type', 'N/A')}\n"
            summary += f"- Date: {case_id.get('decision_date', 'N/A')}\n"
            summary += f"- Bench: {case_id.get('bench_composition', 'N/A')}\n"

            ratios = d1.get("ratio_decidendi", [])
            for r in ratios:
                if isinstance(r, dict):
                    summary += f"- RATIO [{r.get('ratio_id', '')}]: {r.get('label', '')} — {r.get('proposition', '')}\n"

            provisions = d1.get("provisions_engaged", [])
            prov_names = []
            for p in provisions[:5]:
                if isinstance(p, dict):
                    prov_names.append(p.get("provision_id", "") or p.get("parent_statute", ""))
            if prov_names:
                summary += f"- PROVISIONS: {', '.join(prov_names)}\n"

            d4 = genome.get("dimension_4_weaponizable", {})
            sword_uses = d4.get("sword_uses", [])
            for s in sword_uses[:2]:
                if isinstance(s, dict):
                    summary += f"- SWORD: {s.get('scenario', '')}\n"

            shield_uses = d4.get("shield_uses", [])
            for s in shield_uses[:2]:
                if isinstance(s, dict):
                    summary += f"- SHIELD: {s.get('attack_being_faced', s.get('scenario', ''))}\n"

            vuln = d4.get("vulnerability_map", {})
            vulns = vuln.get("vulnerabilities", vuln.get("attack_vectors", []))
            for v in vulns[:2]:
                if isinstance(v, dict):
                    summary += f"- VULNERABILITY: {v.get('weak_point', '')}\n"

            d5 = genome.get("dimension_5_synthesis", {})
            cheat = d5.get("practitioners_cheat_sheet", {})
            cite_when = cheat.get("cite_when", [])
            if isinstance(cite_when, list) and cite_when:
                summary += f"- CITE WHEN: {'; '.join(str(c) for c in cite_when[:3])}\n"
            elif isinstance(cite_when, str) and cite_when:
                summary += f"- CITE WHEN: {cite_when[:200]}\n"

            dont_cite = cheat.get("do_not_cite_when", cheat.get("dont_cite_when", []))
            if isinstance(dont_cite, list) and dont_cite:
                summary += f"- DONT CITE WHEN: {'; '.join(str(c) for c in dont_cite[:3])}\n"
            elif isinstance(dont_cite, str) and dont_cite:
                summary += f"- DONT CITE WHEN: {dont_cite[:200]}\n"

            killer = cheat.get("killer_paragraph", "")
            if killer:
                summary += f"- KILLER PARA: {str(killer)[:300]}\n"

        except Exception as e:
            summary += f"- [Error extracting: {e}]\n"

        parts.append(summary)

    return "\n".join(parts)
