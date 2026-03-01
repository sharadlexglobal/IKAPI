"""
Auto-Tagger — assigns taxonomy categories and topics to genomes
based on provisions_engaged, ratio_decidendi, and cheat sheet data.
No AI calls — pure string matching against provision index and topic keywords.
"""
import logging
from db import (
    get_db_connection, get_cached_genome,
    find_provision_by_alias, tag_genome_category, tag_genome_topic,
    clear_genome_tags, get_taxonomy_topics,
)
from taxonomy_seed import statute_to_category

logger = logging.getLogger(__name__)


def _extract_provision_ids(genome_json):
    d1 = genome_json.get("dimension_1_visible", {})
    provisions = d1.get("provisions_engaged", [])
    results = []
    if isinstance(provisions, list):
        for p in provisions:
            if isinstance(p, dict):
                pid = p.get("provision_id", "")
                statute = p.get("parent_statute", "")
                if pid and not pid.startswith("PROV_"):
                    results.append({"provision_id": pid, "parent_statute": statute})
                elif statute:
                    results.append({"provision_id": None, "parent_statute": statute})
    return results


def _extract_text_for_matching(genome_json):
    texts = []
    d1 = genome_json.get("dimension_1_visible", {})
    ratios = d1.get("ratio_decidendi", [])
    if isinstance(ratios, list):
        for r in ratios:
            if isinstance(r, dict):
                prop = r.get("proposition", "")
                if prop:
                    texts.append(prop.lower())

    d5 = genome_json.get("dimension_5_synthesis", {})
    cheat = d5.get("practitioners_cheat_sheet", {})
    if isinstance(cheat, dict):
        for field in ["cite_when", "dont_cite_when", "killer_paragraph", "hidden_gem"]:
            val = cheat.get(field, "")
            if isinstance(val, str) and val:
                texts.append(val.lower())

    d4 = genome_json.get("dimension_4_weaponizable", {})
    sword = d4.get("sword_shield_index", {})
    if isinstance(sword, dict):
        for key in ["as_sword", "as_shield"]:
            entries = sword.get(key, [])
            if isinstance(entries, list):
                for e in entries:
                    if isinstance(e, dict):
                        label = e.get("label", "")
                        if label:
                            texts.append(label.lower())

    return " ".join(texts)


def tag_genome(tid, genome_json=None):
    if genome_json is None:
        cached = get_cached_genome(tid)
        if not cached:
            logger.warning(f"No genome found for TID {tid}")
            return {"categories": [], "topics": []}
        genome_json = cached["genome_json"]

    clear_genome_tags(tid, auto_only=True)

    matched_categories = set()
    provisions = _extract_provision_ids(genome_json)
    for prov in provisions:
        pid = prov["provision_id"]
        statute = prov["parent_statute"]

        if pid:
            found = find_provision_by_alias(pid)
            if found and found.get("category_id"):
                cat_id = found["category_id"]
                matched_categories.add(cat_id)
                tag_genome_category(tid, cat_id, auto_tagged=True)

        if statute:
            cat_id = statute_to_category(statute)
            if cat_id and cat_id not in matched_categories:
                matched_categories.add(cat_id)
                tag_genome_category(tid, cat_id, auto_tagged=True)

    combined_text = _extract_text_for_matching(genome_json)

    has_category_match = len(matched_categories) > 0
    min_confidence = 0.3 if has_category_match else 0.5

    matched_topics = []
    all_topics = get_taxonomy_topics()
    for topic in all_topics:
        topic_cat = topic.get("category_id", "")
        keywords = topic.get("keywords", [])
        if not keywords:
            continue

        if has_category_match and topic_cat and topic_cat not in matched_categories:
            continue

        matched_kws = 0
        for kw in keywords:
            if kw.lower() in combined_text:
                matched_kws += 1

        if matched_kws == 0:
            continue

        confidence = min(1.0, matched_kws / max(3, len(keywords) * 0.4))
        if confidence >= min_confidence:
            tag_genome_topic(tid, topic["id"], auto_tagged=True, confidence=round(confidence, 2))
            matched_topics.append({"topic_id": topic["id"], "confidence": round(confidence, 2)})

    logger.info(f"Tagged TID {tid}: {len(matched_categories)} categories, {len(matched_topics)} topics")
    return {"categories": list(matched_categories), "topics": matched_topics}


def tag_all_genomes():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT tid, genome_json FROM judgment_genomes")
            rows = cur.fetchall()
    finally:
        conn.close()

    results = {"total": len(rows), "tagged": 0, "categories_assigned": 0, "topics_assigned": 0}
    for tid, genome_json in rows:
        try:
            result = tag_genome(tid, genome_json)
            results["tagged"] += 1
            results["categories_assigned"] += len(result["categories"])
            results["topics_assigned"] += len(result["topics"])
        except Exception as e:
            logger.error(f"Failed to tag TID {tid}: {e}")

    logger.info(f"Auto-tag complete: {results}")
    return results


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    logging.basicConfig(level=logging.INFO)

    from taxonomy_seed import run_seed
    run_seed()
    print()

    print("=== Auto-tagging all genomes ===")
    result = tag_all_genomes()
    print(f"\nResults:")
    print(f"  Total genomes: {result['total']}")
    print(f"  Successfully tagged: {result['tagged']}")
    print(f"  Categories assigned: {result['categories_assigned']}")
    print(f"  Topics assigned: {result['topics_assigned']}")
