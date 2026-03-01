import json
import logging
import os
import anthropic

logger = logging.getLogger(__name__)

CONFLICT_SCAN_SYSTEM = """You are a Senior Legal Analyst specializing in identifying contradictions, tensions, and conflicts between Indian court judgments on the same legal topic.

You have been provided with structured genome extractions from multiple judgments. Your task is to identify ALL conflicts, contradictions, and tensions between them.

TYPES OF CONFLICTS TO DETECT:
1. RATIO_CONTRADICTION: Two judgments state opposing legal propositions on the same issue
2. SWORD_SHIELD_CONFLICT: What one judgment uses as a sword (offensive argument) is contradicted by another judgment's shield (defensive argument)
3. TEMPORAL_SHIFT: The law has shifted over time — earlier judgments say one thing, later ones say another
4. COURT_HIERARCHY_CONFLICT: A lower court judgment contradicts a higher court's position

FOR EACH CONFLICT:
- Identify the exact propositions that conflict
- Rate severity (HIGH = directly contradictory ratios, MEDIUM = tension in application, LOW = minor divergence)
- Provide a resolution strategy for advocates
- Suggest what action an advocate should take

CRITICAL RULES:
1. Reference TIDs precisely
2. Only flag GENUINE conflicts — not merely different facts leading to different outcomes
3. Be specific about which ratio/sword/shield is in conflict
4. Overall coherence: rate whether the body of law is CONSISTENT, has MINOR_TENSIONS, has SIGNIFICANT_CONFLICTS, or is CONTRADICTORY

OUTPUT: Respond with ONLY valid JSON matching the schema below. No markdown fences."""

CONFLICT_SCAN_SCHEMA = """{
  "topic_id": "string",
  "total_genomes_scanned": number,
  "conflicts": [
    {
      "conflict_id": "string (e.g. CONFLICT_1)",
      "severity": "HIGH / MEDIUM / LOW",
      "type": "RATIO_CONTRADICTION / SWORD_SHIELD_CONFLICT / TEMPORAL_SHIFT / COURT_HIERARCHY_CONFLICT",
      "genome_a": {"tid": number, "case_name": "string", "position": "string (the proposition/position taken)"},
      "genome_b": {"tid": number, "case_name": "string", "position": "string (the conflicting proposition/position)"},
      "description": "string (explain the conflict clearly)",
      "resolution_strategy": "string (how an advocate should handle this conflict)",
      "advocate_action": "string (specific action item)"
    }
  ],
  "overall_coherence": "CONSISTENT / MINOR_TENSIONS / SIGNIFICANT_CONFLICTS / CONTRADICTORY"
}"""


def scan_conflicts(topic_id):
    from db import get_topic_genomes_with_json, get_conflict_scan, save_conflict_scan

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    genomes = get_topic_genomes_with_json(topic_id)
    if not genomes:
        raise ValueError(f"No genomes found for topic {topic_id}")

    if len(genomes) < 2:
        result = {
            "topic_id": topic_id,
            "total_genomes_scanned": len(genomes),
            "conflicts": [],
            "overall_coherence": "CONSISTENT",
        }
        save_conflict_scan(topic_id, None, result, "none", len(genomes))
        return result, {"cached": False, "skipped": True}

    cached = get_conflict_scan(topic_id)
    if cached and cached.get("genome_count") == len(genomes):
        return cached["scan_json"], {"cached": True}

    genome_summaries = _prepare_conflict_summaries(genomes)

    user_message = f"""## CONFLICT SCAN SCHEMA
{CONFLICT_SCAN_SCHEMA}

## TOPIC ID: {topic_id}

## GENOMES TO SCAN ({len(genomes)} judgments)
{genome_summaries}

Scan for ALL conflicts, contradictions, and tensions between these judgments. Respond with ONLY valid JSON."""

    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=model,
        max_tokens=16000,
        system=CONFLICT_SCAN_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
        timeout=300,
    )

    response_text = message.content[0].text.strip()
    if response_text.startswith("```"):
        response_text = response_text.strip("`").strip()
        if response_text.startswith("json"):
            response_text = response_text[4:].strip()

    scan_result = json.loads(response_text)

    usage = {}
    if hasattr(message, "usage"):
        usage = {
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
            "model": model, "cached": False,
        }

    save_conflict_scan(topic_id, None, scan_result, model, len(genomes))
    return scan_result, usage


def _prepare_conflict_summaries(genomes):
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

            ratios = d1.get("ratio_decidendi", [])
            for r in ratios:
                if isinstance(r, dict):
                    summary += f"- RATIO [{r.get('ratio_id', '')}]: {r.get('proposition', '')}\n"

            d4 = genome.get("dimension_4_weaponizable", {})
            sword_uses = d4.get("sword_uses", [])
            for s in sword_uses:
                if isinstance(s, dict):
                    summary += f"- SWORD: {s.get('scenario', '')} — {s.get('how_to_cite', '')[:200]}\n"

            shield_uses = d4.get("shield_uses", [])
            for s in shield_uses:
                if isinstance(s, dict):
                    summary += f"- SHIELD: {s.get('attack_being_faced', s.get('scenario', ''))} — {s.get('how_judgment_helps', '')[:200]}\n"

            d5 = genome.get("dimension_5_synthesis", {})
            cheat = d5.get("practitioners_cheat_sheet", {})
            cite_when = cheat.get("cite_when", [])
            if isinstance(cite_when, list) and cite_when:
                summary += f"- CITE WHEN: {'; '.join(str(c) for c in cite_when[:3])}\n"
            dont_cite = cheat.get("do_not_cite_when", cheat.get("dont_cite_when", []))
            if isinstance(dont_cite, list) and dont_cite:
                summary += f"- DONT CITE: {'; '.join(str(c) for c in dont_cite[:3])}\n"

        except Exception as e:
            summary += f"- [Error: {e}]\n"

        parts.append(summary)

    return "\n".join(parts)
