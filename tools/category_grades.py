"""Read-only, two-project test of exposing existing category-grade evidence as weighted ppm."""

import hashlib
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pymupdf

from au_ree_v2.tabular import read_csv
from tools.normalization_comparison import selected_pdf_sources


JUPITER = "bc93c9d96bccf1d5badff0508915633117c723f7858ccddbfedb8a3be938ef7e"
SPLINTER = "56b1bb55bef057af81a1d31faa701e69bef70c9eb95fc7d46ffd1174f5186ca9"
JUPITER_ID = "AU-dac3c8e40326b8244cdb"
SPLINTER_ID = "AU-2262a37ca19531f08da3"
JUPITER_STATEMENT = "jupiter-2026-10-12"
SPLINTER_STATEMENT = "splinter_global_202405"
OXIDES = "La2O3 CeO2 Pr6O11 Nd2O3 Sm2O3 Eu2O3 Gd2O3 Tb4O7 Dy2O3 Ho2O3 Er2O3 Tm2O3 Yb2O3 Lu2O3 Y2O3".split()
PEER_OXIDES = ["Pr6O11", "Nd2O3", "Tb4O7", "Dy2O3"]
MASS_RULE = "SUM_SAME_CUTOFF_CATEGORY_OXIDE_MASSES"
GRADE_BASIS = "RESOURCE_ORE_GRADE_OXIDE_PPM"
CATEGORY = "INDICATED_INFERRED_TOTAL"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _source_pages(assets, sha, pages):
    data = (assets / sha).read_bytes()
    require(hashlib.sha256(data).hexdigest() == sha, f"Original hash mismatch: {sha}")
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        return ["\n".join(" ".join(line.split()) for line in pdf[page - 1].get_text(sort=True).splitlines())
                for page in pages]


def _jupiter_table(text):
    header = "Cut- Million TREO MREO " + " ".join(OXIDES) + " Sc2O3 Ga2O3 Fe"
    require(header in text and "Table 8 | Jupiter" in text, "Jupiter oxide columns changed")
    sections = text.split("Indicated Resources", 1)[1].split("Inferred Resources", 1)
    result = {}
    for category, section in zip(("INDICATED", "INFERRED"), sections, strict=True):
        # Use the 1,000 ppm row, never the cross-category rounded 1.7 Bt headline.
        matches = re.findall(r"^1000 +((?:[\d,.]+ +){20}[\d,.]+)$", section, re.MULTILINE)
        require(len(matches) == 1, f"Missing or ambiguous 1,000 ppm row for {category}")
        numbers = [Decimal(t.replace(",", "")) for t in matches[0].split()]
        result[category] = (numbers[0], numbers[1], dict(zip(OXIDES, numbers[3:18], strict=True)))
    return result


def _peer_table(text):
    text = " ".join(text.split())
    header = "Tonnes TREO " + " ".join(PEER_OXIDES) + " MREO"
    require(header in text and "at 1,000ppm TREO cut off grade" in text, "Splinter Rock cutoff or headings changed")
    matches = re.findall(r"Indicated Total 682 1,338 (\d+) (\d+) (\d+) (\d+) 307 22.9% & Inferred", text)
    require(len(matches) == 1, "Splinter Rock combined resource total missing")
    return dict(zip(PEER_OXIDES, map(Decimal, matches[0]), strict=True))


def weighted_grade(observation, table):
    """Validate both source categories and reconcile the admitted contained mass before conversion."""
    oxide = observation["basis"]
    require(observation["material_basis"] == "RESOURCE_CONTAINED_OXIDE_MASS_KT"
            and observation["unit"] == "kt" and observation["category"] == CATEGORY
            and observation["variable"] == f"reported_resource_contained_{oxide.lower()}_kt",
            "Incompatible resource observation")
    transform = json.loads(observation["source_transform"], parse_float=Decimal)
    parts = transform["categories"]
    require(transform["rule"] == MASS_RULE and transform["cutoff_treo_ppm"] == 1000
            and len(parts) == 2 and {p["category"] for p in parts} == {"INDICATED", "INFERRED"},
            "Category coverage or TREO cutoff mismatch")
    ore_mt = Decimal(0)
    oxide_mt_ppm = Decimal(0)
    for part in parts:
        tonnes, treo, grades = table[part["category"]]
        require(part["cutoff_treo_ppm"] == 1000 and part["ore_mt"] == tonnes > 0
                and part["treo_ppm"] == treo and part["oxide_ppm"] == grades[oxide],
                "Category observation disagrees with PDF row")
        ore_mt += tonnes
        oxide_mt_ppm += tonnes * grades[oxide]
    require(oxide_mt_ppm / 1000 == Decimal(observation["value"]), "Contained mass mismatch")
    return oxide_mt_ppm / ore_mt


def _linked(row, lineage, statement, page, role, cutoff):
    require(row["statement_id"] == statement and row["category"] == CATEGORY and row["physical_page"] == str(page)
            and row["selection_role"] == role and row["statement_kind"] == "RESOURCE_CONTEXT"
            and row["scope"] and row["effective_date"] <= cutoff and row["publication_date"] <= cutoff
            and row["effective_date"] and row["publication_date"], "Source context changed")
    require(len(lineage) == 1 and row["observation_id"] in json.loads(lineage[0]["supporting_observation_ids"])
            and row["source_statement_key"] in json.loads(lineage[0]["source_statement_keys"])
            and row["source_sha256"] == lineage[0]["source_sha256"]
            and row["statement_group_id"] == lineage[0]["statement_group_id"], "Missing source lineage")


def run(release, assets):
    """Return descriptive comparison diagnostics. Reads existing export and content-addressed PDFs."""
    release, assets = Path(release), Path(assets)
    approved = selected_pdf_sources(release)
    require({JUPITER, SPLINTER} <= approved.keys(), "Original missing from verified within-cutoff PDF selection")
    cutoff = approved[JUPITER]
    note, table_text = _source_pages(assets, JUPITER, (3, 19))
    require("Gallium and scandium are excluded from TREO" in note, "Jupiter TREO definition changed")
    peer_text, = _source_pages(assets, SPLINTER, (2,))
    require("Lu2O3 + Y2O3" in peer_text and "La2O3 + CeO2" in peer_text, "Splinter TREO definition changed")
    table, peer = _jupiter_table(table_text), _peer_table(peer_text)
    rows = [r for r in read_csv(release / "resource_statement_observations.csv") if r["selected_for_census"] == "1"]
    lineage = read_csv(release / "resource_statement_lineage.csv")
    candidates = [r for r in rows if r["project_id"] == JUPITER_ID and r["source_sha256"] == JUPITER
                  and r["material_basis"] == "RESOURCE_CONTAINED_OXIDE_MASS_KT"]
    require(len(candidates) == len(OXIDES) and {r["basis"] for r in candidates} == set(OXIDES), "Duplicate or missing Jupiter oxide")
    # Each displayed grade has the same whole-ppm resolution as the source categories.
    # Keep both source grades and tonnages so the unrounded weighted result is reproducible.
    views, comparisons = [], []
    peer_dates = set()
    for row in sorted(candidates, key=lambda item: item["basis"]):
        oxide = row["basis"]
        def links(project, method):
            return [l for l in lineage if l["project_id"] == project and l["method"] == method
                    and l["column"].startswith(oxide + "_")]
        _linked(row, links(JUPITER_ID, MASS_RULE), JUPITER_STATEMENT, 19, "VERIFIED_EQUIVALENT_SOURCE", cutoff)
        grade = weighted_grade(row, table)
        # Any pre-existing selected ppm observation for this oxide suppresses the novelty claim.
        existing = any(r["project_id"] == JUPITER_ID and r["basis"] == oxide and r["unit"] == "ppm"
                       and r["material_basis"] == GRADE_BASIS and r["category"] == CATEGORY for r in rows)
        view = {"oxide": oxide, "weighted_ppm": str(grade.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
                "category_ppm": {name: str(values[2][oxide]) for name, values in table.items()},
                "jupiter_observation": row["observation_id"],
                "already_present": existing}
        views.append(view)
        if oxide not in peer:
            continue
        matches = [r for r in rows if r["project_id"] == SPLINTER_ID and r["source_sha256"] == SPLINTER
                   and r["unit"] == "ppm" and r["basis"] == oxide and r["material_basis"] == GRADE_BASIS]
        require(len(matches) == 1, "Peer grade missing or ambiguous")
        other = matches[0]
        _linked(other, links(SPLINTER_ID, "ORE_MT_X_OXIDE_PPM_X_0_001"), SPLINTER_STATEMENT, 2,
                "MATCHED_SELECTED_STATEMENT", cutoff)
        require(other["original_unit"] == "ppm" and not other["source_transform"]
                and Decimal(other["original_token"]) == Decimal(other["value"]) == peer[oxide], "Peer grade mismatch")
        peer_dates.add(other["effective_date"])
        comparisons.append({**view, "splinter_ppm": str(peer[oxide]), "splinter_observation": other["observation_id"]})
    require(len(peer_dates) == 1, "Inconsistent peer estimate dates")
    return {"jupiter_sha256": JUPITER, "jupiter_page": 19, "jupiter_statement_date": candidates[0]["effective_date"],
            "splinter_sha256": SPLINTER, "splinter_page": 2, "splinter_statement_date": peer_dates.pop(),
            "category": CATEGORY, "unit": "ppm oxide in bulk ore",
            "category_ore_mt": {name: str(values[0]) for name, values in table.items()},
            "sum_of_reported_category_tonnes_mt": str(sum(item[0] for item in table.values())),
            "limit": "Issuer-specific reporting envelopes at nominal 1,000 ppm TREO. Splinter explicitly includes Y and Ce; Jupiter excludes Sc and Ga but does not specify the full cutoff oxide sum. Descriptive oxide grades only; source rounding applies.",
            "weighted_views": views, "pairs": comparisons, "baseline_oxide_pairs": sum(p["already_present"] for p in comparisons),
            "after_oxide_pairs": len(comparisons), "new_oxide_pairs": sum(not p["already_present"] for p in comparisons),
            "matched_project_pairs": int(bool(comparisons)), "equal_cutoff_composition_pairs": 0}
