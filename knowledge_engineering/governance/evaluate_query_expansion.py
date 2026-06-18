"""Audit query_expansion.yaml against the KE golden query set.

This script is intentionally read-only: it parses the Markdown golden set,
loads ontology/query_expansion.yaml, and reports which expansion edges are
helpful, missing, or noisy. It does not rewrite ontology files or mark rules
verified/rejected.

Run:
    python -m knowledge_engineering.governance.evaluate_query_expansion
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from knowledge_engineering.enrichment.query_demo import parse_concepts


ROOT = Path(__file__).resolve().parents[2]
GOLDEN_MD = ROOT / "docs2/reports/ontology/sprint1/golden_query_concepts.md"
EXPANSION_YAML = ROOT / "ontology/query_expansion.yaml"


@dataclass
class GoldenQuery:
    qid: str
    title: str
    query: str
    expected_concepts: set[str]
    expected_ranges: dict[str, Any]
    expected_expansion: set[str]
    hotel_ids: list[int]
    intent: str
    note: str


def strip_jsonc_comments(text: str) -> str:
    """Remove // and /* */ comments while preserving quoted strings."""
    out: list[str] = []
    i = 0
    in_str = False
    escape = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_str:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def flatten_concepts(value: Any) -> set[str]:
    if not isinstance(value, dict):
        return set()
    out: set[str] = set()
    for item in value.values():
        if isinstance(item, list):
            out.update(str(x) for x in item)
        elif isinstance(item, str):
            out.add(item)
    return out


def parse_golden(path: Path = GOLDEN_MD) -> list[GoldenQuery]:
    text = path.read_text(encoding="utf-8")
    heading_re = re.compile(r"^###\s+(Q\d+-\d+)\s+—\s+(.+)$", re.MULTILINE)
    matches = list(heading_re.finditer(text))
    out: list[GoldenQuery] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        section = text[start:end]
        fence = re.search(r"```jsonc\s*(.*?)```", section, re.DOTALL)
        if not fence:
            continue
        raw_json = strip_jsonc_comments(fence.group(1)).strip()
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Cannot parse JSONC block for {match.group(1)}") from exc
        out.append(
            GoldenQuery(
                qid=match.group(1),
                title=match.group(2).strip(),
                query=data.get("query", ""),
                expected_concepts=flatten_concepts(data.get("expected_concepts", {})),
                expected_ranges=data.get("expected_range_filters", {}) or {},
                expected_expansion=set(data.get("expansion_should_help", []) or []),
                hotel_ids=[int(x) for x in data.get("hotel_ids", []) or []],
                intent=data.get("_intent", "") or "",
                note=data.get("_note", "") or "",
            )
        )
    return out


def load_rules(path: Path = EXPANSION_YAML) -> dict[str, set[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = data.get("rules", {}) or {}
    return {src: set((rule or {}).get("expands_to", []) or []) for src, rule in rules.items()}


def expand_once(concepts: set[str], rules: dict[str, set[str]]) -> set[str]:
    out: set[str] = set()
    for concept in concepts:
        out.update(rules.get(concept, set()))
    return out - concepts


def classify_query(row: dict[str, Any]) -> str:
    """Classify a row for human audit, not as a retrieval verdict."""
    expected = set(row["expected_concepts"])
    parsed = set(row["parsed_concepts"])
    wanted = set(row["wanted_expansion"])
    missing_expected = expected - parsed
    missing_expansion = set(row["missing_from_parsed_trigger"])
    parsed_extra = set(row["parsed_extra"])
    intent = row["intent"]

    # These queries require a router before concept parsing: hotel detail, room,
    # nearby/activity, compare, or combo flows should not be treated as plain
    # hotel-discovery searches.
    router_prefixes = (
        "hotel_", "room_", "nearby_", "activities_", "compare_", "similar_",
        "combo_",
    )
    if intent.startswith(router_prefixes):
        if expected and all(c.startswith("ASPECT_") for c in expected):
            return "out_of_scope_for_concept_parser"
        return "intent_router_needed"

    # Aspect-only expectations are review/ranking semantics, not hard filters.
    if expected and all(c.startswith("ASPECT_") for c in expected):
        return "out_of_scope_for_concept_parser"

    if missing_expected or missing_expansion:
        return "parser_miss"
    if not wanted and parsed_extra:
        return "expansion_risk_if_filter"
    return "ok"


def evaluate() -> dict[str, Any]:
    golden = parse_golden()
    rules = load_rules()
    rows: list[dict[str, Any]] = []
    rule_stats: dict[str, dict[str, Any]] = {
        src: {"target_hits": {}, "noise_queries": [], "trigger_queries": []}
        for src in rules
    }

    for gq in golden:
        parsed, implicit = parse_concepts(gq.query)
        parsed_set = set(parsed)
        expected_added = expand_once(gq.expected_concepts, rules)
        parsed_added = expand_once(parsed_set, rules)
        expected_hits = expected_added & gq.expected_expansion
        parsed_hits = parsed_added & gq.expected_expansion
        missing_from_expected_trigger = gq.expected_expansion - expected_added
        missing_from_parsed_trigger = gq.expected_expansion - parsed_added
        expected_extra = expected_added - gq.expected_expansion
        parsed_extra = parsed_added - gq.expected_expansion

        for src in sorted(gq.expected_concepts & set(rules)):
            stat = rule_stats[src]
            stat["trigger_queries"].append(gq.qid)
            for tgt in sorted(rules[src]):
                if tgt in gq.expected_expansion:
                    stat["target_hits"][tgt] = stat["target_hits"].get(tgt, 0) + 1
                elif not gq.expected_expansion:
                    stat["noise_queries"].append(gq.qid)

        rows.append(
            {
                "qid": gq.qid,
                "query": gq.query,
                "intent": gq.intent,
                "note": gq.note,
                "expected_concepts": sorted(gq.expected_concepts),
                "expected_range_filters": gq.expected_ranges,
                "parsed_concepts": sorted(parsed_set),
                "implicit": implicit,
                "wanted_expansion": sorted(gq.expected_expansion),
                "expected_trigger_added": sorted(expected_added),
                "parsed_trigger_added": sorted(parsed_added),
                "expected_hits": sorted(expected_hits),
                "parsed_hits": sorted(parsed_hits),
                "missing_from_expected_trigger": sorted(missing_from_expected_trigger),
                "missing_from_parsed_trigger": sorted(missing_from_parsed_trigger),
                "expected_extra": sorted(expected_extra),
                "parsed_extra": sorted(parsed_extra),
            }
        )
        rows[-1]["classification"] = classify_query(rows[-1])

    helpful_queries = [r for r in rows if r["wanted_expansion"]]
    negative_queries = [r for r in rows if not r["wanted_expansion"]]
    return {
        "n_queries": len(rows),
        "n_helpful_queries": len(helpful_queries),
        "n_negative_queries": len(negative_queries),
        "n_rules": len(rules),
        "queries": rows,
        "rule_stats": rule_stats,
    }


def print_summary(report: dict[str, Any], show_all: bool = False) -> None:
    print(
        f"Queries: {report['n_queries']} | helpful: {report['n_helpful_queries']} | "
        f"negative: {report['n_negative_queries']} | rules: {report['n_rules']}"
    )
    counts: dict[str, int] = {}
    for row in report["queries"]:
        counts[row["classification"]] = counts.get(row["classification"], 0) + 1
    print("Classification:", dict(sorted(counts.items())))
    print()
    print("Per-query classification:")
    for row in report["queries"]:
        print(f"- {row['qid']}: {row['classification']}")
        if show_all:
            print(f"  query : {row['query']}")
            print(f"  expect: {row['expected_concepts']}")
            print(f"  parsed: {row['parsed_concepts']}")
            print(f"  want expansion: {row['wanted_expansion']}")
            print(f"  parsed expansion: {row['parsed_trigger_added']}")
            if row["intent"]:
                print(f"  intent: {row['intent']}")
            if row["note"]:
                print(f"  note  : {row['note']}")
    print()
    print("Helpful expansion queries:")
    for row in report["queries"]:
        if not row["wanted_expansion"]:
            continue
        print(f"- {row['qid']}: {row['query']}")
        print(f"  wanted : {row['wanted_expansion']}")
        print(f"  parsed : {row['parsed_concepts']}")
        print(f"  added  : {row['parsed_trigger_added']}")
        print(f"  hits   : {row['parsed_hits'] or '[]'}")
        print(f"  missing: {row['missing_from_parsed_trigger'] or '[]'}")
        print(f"  extra  : {row['parsed_extra'] or '[]'}")
    print()
    print("Negative queries where parsed-trigger expansion adds concepts:")
    noisy = [
        row for row in report["queries"]
        if not row["wanted_expansion"] and row["parsed_trigger_added"]
    ]
    for row in noisy if show_all else noisy[:12]:
        print(f"- {row['qid']}: added={row['parsed_trigger_added']} | parsed={row['parsed_concepts']}")
    if not noisy:
        print("- none")
    elif not show_all and len(noisy) > 12:
        print(f"- ... {len(noisy) - 12} more (use --all)")
    print()
    print("Rules triggered by expected concepts:")
    for src, stat in sorted(report["rule_stats"].items()):
        if not stat["trigger_queries"]:
            continue
        hits = stat["target_hits"]
        noise = sorted(set(stat["noise_queries"]))
        print(f"- {src}: triggers={sorted(set(stat['trigger_queries']))} hits={hits or '{}'} noise={noise or '[]'}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--all", action="store_true", help="show all noisy negative queries")
    args = parser.parse_args()
    report = evaluate()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_summary(report, show_all=args.all)


if __name__ == "__main__":
    main()
