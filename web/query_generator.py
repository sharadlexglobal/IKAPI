"""
Query Generator — converts legal research questions into Indian Kanoon search queries.
Uses Claude Haiku for fast, cheap query generation.
"""
import json
import logging
import os
import anthropic

logger = logging.getLogger(__name__)

QUERY_GEN_SYSTEM = """You are an expert Indian legal researcher who converts legal research questions into optimized Indian Kanoon (indiankanoon.org) search queries.

INDIAN KANOON SEARCH SYNTAX:
- Phrase search: use double quotes, e.g. "right to privacy"
- AND: multiple words are implicitly AND. Use explicit AND only when needed
- OR: use ORR (case-sensitive), e.g. murder ORR kidnapping
- NOT: use NOTT, e.g. bail NOTT anticipatory
- Title filter: title: word
- Author/Judge filter: author: judge_name
- Court filter: docsource: court_name

AVAILABLE DOCTYPES:
- supremecourt, delhi, bombay, kolkata, chennai, allahabad, andhra, chattisgarh, gauhati, kerala, lucknow, orissa, gujarat, himachal_pradesh, jharkhand, karnataka, madhyapradesh, patna, punjab, rajasthan, sikkim
- Aggregators: judgments (all courts), highcourts (all HCs)
- Tribunals: cat, itat, consumer, greentribunal, cci, drat, tdsat, cerc

SORT OPTIONS: mostcited (best for finding authoritative precedents)

YOUR TASK:
Given a legal research question and case context, generate 1-2 optimized IK search queries.

STRATEGY:
1. Extract statutory provisions (Section X of Act Y) — use exact text in quotes
2. Extract legal concepts — use precise legal terminology
3. Prefer "mostcited" sort for precedent questions
4. For the primary query, focus on the core legal proposition
5. For the alternate query (if provided), try a broader or narrower variation
6. Choose appropriate doctype based on court hierarchy relevance

RESPOND WITH ONLY THIS JSON (no markdown, no explanation):
{
  "queries": [
    {
      "ik_query": "formatted search string",
      "doctype": "one of the available doctypes or empty string",
      "sort": "mostcited or empty string",
      "rationale": "one-line explanation of query strategy"
    }
  ]
}

CRITICAL RULES:
1. Maximum 2 queries per question
2. Keep queries focused — do not make them too broad or too narrow
3. Use double quotes for exact phrases in the query
4. Always include at least one query with "mostcited" sort for precedent discovery
5. If the question mentions a specific court, use that as doctype
6. If no specific court, prefer "supremecourt" for constitutional questions, "judgments" for general
7. Extract the LEGAL CONCEPT, not the full question text"""


def generate_queries_for_question(question_text, question_category, case_context=None):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not configured")
        return []

    context_str = ""
    if case_context:
        parts = []
        if case_context.get("court"):
            parts.append(f"Court: {case_context['court']}")
        if case_context.get("pleading_type"):
            parts.append(f"Pleading Type: {case_context['pleading_type']}")
        if case_context.get("client_side"):
            parts.append(f"Client Side: {case_context['client_side']}")
        if case_context.get("reliefs_sought"):
            parts.append(f"Reliefs: {', '.join(case_context['reliefs_sought'][:3])}")
        if parts:
            context_str = "\n\nCASE CONTEXT:\n" + "\n".join(parts)

    user_msg = f"QUESTION CATEGORY: {question_category}\n\nRESEARCH QUESTION: {question_text}{context_str}"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            system=QUERY_GEN_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            timeout=30,
        )
        response_text = message.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.strip("`").strip()
            if response_text.startswith("json"):
                response_text = response_text[4:].strip()

        data = json.loads(response_text)
        return data.get("queries", [])
    except json.JSONDecodeError as e:
        logger.warning(f"Query gen JSON parse failed: {e}")
        return _fallback_query(question_text, question_category)
    except Exception as e:
        logger.warning(f"Query gen failed: {e}")
        return _fallback_query(question_text, question_category)


def generate_queries_batch(questions, case_context=None):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {}

    context_str = ""
    if case_context:
        parts = []
        if case_context.get("court"):
            parts.append(f"Court: {case_context['court']}")
        if case_context.get("pleading_type"):
            parts.append(f"Pleading Type: {case_context['pleading_type']}")
        if parts:
            context_str = "\nCASE CONTEXT: " + "; ".join(parts)

    batch_prompt = f"""Generate Indian Kanoon search queries for each of the following research questions.{context_str}

For EACH question, produce 1-2 optimized search queries.

RESPOND WITH ONLY THIS JSON (no markdown):
{{
  "results": {{
    "<question_id>": {{
      "queries": [
        {{"ik_query": "...", "doctype": "...", "sort": "mostcited", "rationale": "..."}}
      ]
    }}
  }}
}}

QUESTIONS:
"""
    for q in questions:
        batch_prompt += f"\n[{q['question_id']}] ({q['category']}) {q['text']}"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=4000,
            system=QUERY_GEN_SYSTEM,
            messages=[{"role": "user", "content": batch_prompt}],
            timeout=60,
        )
        response_text = message.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.strip("`").strip()
            if response_text.startswith("json"):
                response_text = response_text[4:].strip()

        data = json.loads(response_text)
        return data.get("results", {})
    except Exception as e:
        logger.warning(f"Batch query gen failed: {e}, falling back to individual")
        results = {}
        for q in questions:
            queries = _fallback_query(q["text"], q["category"])
            results[q["question_id"]] = {"queries": queries}
        return results


def _fallback_query(question_text, category):
    import re
    provisions = re.findall(
        r'(?:Section|Article|Rule|Order|Regulation)\s+[\d\w]+(?:\s+(?:of|under)\s+(?:the\s+)?[\w\s,]+(?:Act|Code|Rules|Constitution))?',
        question_text, re.IGNORECASE
    )

    if provisions:
        query = " ".join(f'"{p.strip()}"' for p in provisions[:3])
    else:
        words = question_text.split()
        key_terms = [w for w in words if len(w) > 4 and w[0].isupper()]
        if len(key_terms) >= 2:
            query = " ".join(f'"{t}"' for t in key_terms[:4])
        else:
            query = " ".join(words[:8])

    doctype = "judgments"
    if "constitution" in question_text.lower() or "article" in question_text.lower():
        doctype = "supremecourt"

    return [{"ik_query": query, "doctype": doctype, "sort": "mostcited", "rationale": "fallback extraction"}]


def deduplicate_queries(all_queries):
    seen = set()
    unique = []
    for q in all_queries:
        key = q.get("ik_query", "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(q)
    return unique
