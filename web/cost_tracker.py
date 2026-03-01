"""
Cost Tracker — tracks Claude API and IK API costs for pipeline runs.
Fixed exchange rate: 1 USD = 95 INR.
"""

USD_TO_INR = 95.0

CLAUDE_PRICING = {
    "claude-3-haiku-20240307": {
        "input_per_million": 0.25,
        "output_per_million": 1.25,
    },
    "claude-sonnet-4-6": {
        "input_per_million": 3.00,
        "output_per_million": 15.00,
    },
    "claude-opus-4-6": {
        "input_per_million": 5.00,
        "output_per_million": 25.00,
    },
}

IK_PRICING_INR = {
    "search": 0.50,
    "original_document": 0.50,
    "document": 0.20,
    "document_fragment": 0.05,
    "document_metainfo": 0.02,
}

IK_PRICING_USD = {k: v / USD_TO_INR for k, v in IK_PRICING_INR.items()}


def calculate_claude_cost(model, input_tokens, output_tokens):
    pricing = CLAUDE_PRICING.get(model)
    if not pricing:
        for key in CLAUDE_PRICING:
            if key in model or model in key:
                pricing = CLAUDE_PRICING[key]
                break
    if not pricing:
        pricing = CLAUDE_PRICING["claude-sonnet-4-6"]

    input_cost = (input_tokens / 1_000_000) * pricing["input_per_million"]
    output_cost = (output_tokens / 1_000_000) * pricing["output_per_million"]
    return round(input_cost + output_cost, 6)


def calculate_ik_cost(search_count=0, document_count=0, original_document_count=0,
                      document_fragment_count=0, document_metainfo_count=0):
    total_inr = (
        search_count * IK_PRICING_INR["search"]
        + document_count * IK_PRICING_INR["document"]
        + original_document_count * IK_PRICING_INR["original_document"]
        + document_fragment_count * IK_PRICING_INR["document_fragment"]
        + document_metainfo_count * IK_PRICING_INR["document_metainfo"]
    )
    return round(total_inr / USD_TO_INR, 6)


def usd_to_inr(usd):
    return round(usd * USD_TO_INR, 2)


def format_cost(usd):
    inr = usd_to_inr(usd)
    return f"${usd:.4f} (₹{inr:.2f})"


class PipelineCostTracker:
    def __init__(self):
        self.breakdown = {
            "question_extraction": {"claude_usd": 0, "input_tokens": 0, "output_tokens": 0, "model": ""},
            "query_generation": {"claude_usd": 0, "input_tokens": 0, "output_tokens": 0, "api_calls": 0, "model": ""},
            "ik_search": {"ik_usd": 0, "search_count": 0},
            "relevance_filtering": {"claude_usd": 0, "input_tokens": 0, "output_tokens": 0, "api_calls": 0, "model": ""},
            "doc_fetching": {"ik_usd": 0, "document_count": 0},
            "genome_extraction": {"claude_usd": 0, "input_tokens": 0, "output_tokens": 0, "api_calls": 0, "model": ""},
            "synthesis": {"claude_usd": 0, "input_tokens": 0, "output_tokens": 0, "model": ""},
        }
        self.total_usd = 0

    def add_claude_cost(self, step, model, input_tokens, output_tokens):
        cost = calculate_claude_cost(model, input_tokens, output_tokens)
        entry = self.breakdown.get(step, {})
        entry["claude_usd"] = round(entry.get("claude_usd", 0) + cost, 6)
        entry["input_tokens"] = entry.get("input_tokens", 0) + input_tokens
        entry["output_tokens"] = entry.get("output_tokens", 0) + output_tokens
        entry["model"] = model
        if "api_calls" in entry:
            entry["api_calls"] = entry.get("api_calls", 0) + 1
        self.breakdown[step] = entry
        self._recalc_total()
        return cost

    def add_ik_search(self, count=1):
        entry = self.breakdown["ik_search"]
        entry["search_count"] = entry.get("search_count", 0) + count
        entry["ik_usd"] = round(calculate_ik_cost(search_count=entry["search_count"]), 6)
        self._recalc_total()

    def add_ik_document(self, count=1):
        entry = self.breakdown["doc_fetching"]
        entry["document_count"] = entry.get("document_count", 0) + count
        entry["ik_usd"] = round(calculate_ik_cost(document_count=entry["document_count"]), 6)
        self._recalc_total()

    def _recalc_total(self):
        total = 0
        for step_data in self.breakdown.values():
            total += step_data.get("claude_usd", 0)
            total += step_data.get("ik_usd", 0)
        self.total_usd = round(total, 6)

    def get_total_usd(self):
        return self.total_usd

    def get_total_inr(self):
        return usd_to_inr(self.total_usd)

    def get_breakdown(self):
        result = {}
        for step, data in self.breakdown.items():
            step_total = round(data.get("claude_usd", 0) + data.get("ik_usd", 0), 6)
            if step_total > 0 or data.get("search_count", 0) > 0 or data.get("document_count", 0) > 0:
                result[step] = {**data, "step_total_usd": step_total, "step_total_inr": usd_to_inr(step_total)}
        result["total_usd"] = self.total_usd
        result["total_inr"] = self.get_total_inr()
        result["exchange_rate"] = USD_TO_INR
        return result
