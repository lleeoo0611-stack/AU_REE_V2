"""Rank pages of one verified edition for resource values and supporting context."""

from itertools import zip_longest

from .nlp import PageIndex


VERSION = "resource-retrieval-bm25-v1"
DEFAULT_VALUE_PAGES = 24
DEFAULT_CONTEXT_PAGES = 32
QUERIES = ("resource", "strategic_composition", "resource_context")


def policy(configured=None, *, override_mode=None):
    """Resolve optional frame policy before opening any originals."""
    if configured is None:
        configured = {}
    keys = {"mode", "value_page_budget", "context_page_budget"}
    if not isinstance(configured, dict) or configured.keys() - keys:
        raise ValueError("INVALID_RESOURCE_RETRIEVAL_POLICY")
    configured_mode = configured.get("mode", "fixed")
    mode = override_mode if override_mode is not None else configured_mode
    if configured_mode not in ("fixed", "full-text") or mode not in ("fixed", "full-text"):
        raise ValueError("INVALID_RESOURCE_RETRIEVAL_MODE")
    value_budget = configured.get("value_page_budget", DEFAULT_VALUE_PAGES)
    context_budget = configured.get("context_page_budget", DEFAULT_CONTEXT_PAGES)
    if any(type(budget) is not int or budget < 1 for budget in (value_budget, context_budget)):
        raise ValueError("INVALID_RESOURCE_RETRIEVAL_PAGE_BUDGET")
    if mode == "fixed":
        return {"mode": "fixed"}
    return {"mode": mode, "version": VERSION, "value_page_budget": value_budget,
            "context_page_budget": context_budget}


def _page_queue(seeds, ranks, budget):
    # Preserve the historical physical scope as the first retrieval arm. A
    # restricted budget cannot silently remove a required fixed seed.
    queue = list(dict.fromkeys([*seeds, *ranks]))
    return queue[:budget], len(queue[budget:])


def retrieve(documents, source, aliases, settings, *, blocked_reason=None):
    """Bind BM25 results to a single selected SHA. Scores never validate evidence."""
    sha = source["source_sha256"]
    fixed_values = source["pages"]
    fixed_context = source.get("context_pages", [])
    value_budget, context_budget = settings["value_page_budget"], settings["context_page_budget"]
    if len(fixed_values) > value_budget or len(fixed_context) > context_budget:
        raise ValueError("RESOURCE_RETRIEVAL_BUDGET_BELOW_FIXED_FRAME")
    receipt = {"source_key": source["source_key"], "source_sha256": sha,
               "document_total_pages": None, "indexed_page_count": 0, "unreadable_pages": [],
               "index_failures": [], "candidate_pages": {field: [] for field in QUERIES},
               "selected_pages": fixed_values, "selected_context_pages": fixed_context,
               "value_pages_over_budget": 0, "context_pages_over_budget": 0,
               "parsed_pages": [], "parsed_context_pages": []}
    missing, issues = {}, {}
    if not blocked_reason:
        index = PageIndex.from_documents(documents, [sha], missing=missing, page_diagnostics=issues)
        blocked_reason = missing.get(sha)
    if blocked_reason:
        return {**receipt, "status": "SOURCE_BLOCKED", "reason": blocked_reason}
    total = len(index.page_keys)
    receipt["document_total_pages"], receipt["indexed_page_count"] = total, len(index.documents)
    for page, status, reason in issues.get(sha, []):
        if status == "PAGE_TEXT_UNREADABLE":
            receipt["unreadable_pages"].append(page)
        else:
            receipt["index_failures"].append({"physical_page": page, "reason": reason})
    if not index.documents:
        return {**receipt, "status": "INDEX_INCOMPLETE", "reason": "NO_SEARCHABLE_PAGE"}
    ranked = {field: [page for _, page in index.rank_pair(aliases, field, k=total)["rules_nlp"]]
              for field in QUERIES}
    # Interleave the resource and composition queries, so each contributes to
    # a bounded value queue even when the other uses common text on many pages.
    combined = [page for row in zip_longest(ranked["resource"], ranked["strategic_composition"])
                for page in row if page is not None]
    values, value_omitted = _page_queue(fixed_values, combined, value_budget)
    context, context_omitted = _page_queue(fixed_context, ranked["resource_context"], context_budget)
    return {**receipt, "status": "SEARCHED", "reason": None,
            "candidate_pages": ranked, "selected_pages": sorted(values), "selected_context_pages": sorted(context),
            "value_pages_over_budget": value_omitted, "context_pages_over_budget": context_omitted}


def apply_parse_receipt(search, result):
    """Distinguish search coverage from pages examined by the native extractor."""
    pages = result.get("pages", [])
    if pages and isinstance(pages[0], dict):
        search["value_page_dispositions"] = pages
        search["parsed_pages"] = [page["physical_page"] for page in pages
                                  if page["status"] in {"DISCOVERED", "NO_CANDIDATES"}]
    support = result.get("context_page_dispositions", [])
    if support:
        search["context_page_dispositions"] = support
        search["parsed_context_pages"] = [page["physical_page"] for page in support
                                          if page["status"] == "PARSED"]
    statuses = {page["status"] for page in pages if isinstance(page, dict)}
    search["native_value_outcome"] = ("DISCOVERED" if "DISCOVERED" in statuses else
                                      "PARSE_FAILED" if "PARSE_FAILED" in statuses else
                                      "EXAMINED_WITHOUT_CANDIDATES" if "NO_CANDIDATES" in statuses else
                                      "NOT_PARSED")
    if "DISCOVERED" in statuses:
        outcome = "VALUE_CANDIDATES_PARSED"
    elif search["status"] == "SOURCE_BLOCKED" or result.get("status") == "SOURCE_BLOCKED":
        outcome = "SOURCE_BLOCKED"
    elif "PARSE_FAILED" in statuses or search["index_failures"]:
        outcome = "PAGE_PARSE_FAILED"
    elif search["value_pages_over_budget"]:
        outcome = "SEARCH_BUDGET_EXHAUSTED"
    elif search["unreadable_pages"]:
        outcome = "SEARCH_INCOMPLETE_UNREADABLE_PAGES"
    elif search["status"] == "INDEX_INCOMPLETE" or "PAGE_UNAVAILABLE" in statuses:
        outcome = "SEARCH_INCOMPLETE"
    elif any(search["candidate_pages"][field] for field in ("resource", "strategic_composition")):
        outcome = "RANKED_PAGES_WITH_NO_EXTRACTABLE_ROWS"
    else:
        outcome = "NO_RELEVANT_VALUE_EVIDENCE_FOUND"
    search["value_search_outcome"] = outcome
    context_statuses = {page["status"] for page in support}
    if outcome == "SOURCE_BLOCKED":
        context_outcome = "SOURCE_BLOCKED"
    elif "PARSE_FAILED" in context_statuses or search["index_failures"]:
        context_outcome = "PAGE_PARSE_FAILED"
    elif search["context_pages_over_budget"]:
        context_outcome = "SEARCH_BUDGET_EXHAUSTED"
    elif "UNREADABLE" in context_statuses or search["unreadable_pages"]:
        context_outcome = "SEARCH_INCOMPLETE_UNREADABLE_PAGES"
    elif search["status"] == "INDEX_INCOMPLETE" or "PAGE_UNAVAILABLE" in context_statuses:
        context_outcome = "SEARCH_INCOMPLETE"
    elif search["parsed_context_pages"]:
        context_outcome = "CONTEXT_PAGES_PARSED"
    else:
        context_outcome = "NO_RELEVANT_CONTEXT_PAGE_FOUND"
    search["context_search_outcome"] = context_outcome
