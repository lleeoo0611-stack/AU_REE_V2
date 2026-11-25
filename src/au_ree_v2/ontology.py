"""Small SKOS/PROV/SHACL experiment over explicitly annotated evidence context.

No NLP, external RDF fetching, database mutation, numeric imputation or fuzzy
entity merging occurs here. Passing a declared-use contract is not proof of
universal comparability or source truth. Original evidence remains upstream.
"""

import json
import math
import re
import unicodedata
from pathlib import Path
from urllib.parse import quote

from .store import canonical, digest


def _label(value):
    # Preserve case: Mt and mt, and Co and CO, must not become equal.
    return " ".join(unicodedata.normalize("NFKC", value).split())


def load_vocabulary(path):
    vocabulary = json.loads(Path(path).read_text(encoding="utf-8"))
    if vocabulary.get("version") != "ree-comparability-ontology-v1":
        raise ValueError("Unsupported ontology vocabulary version")
    if not isinstance(vocabulary.get("namespace"), str) or not vocabulary["namespace"].startswith("urn:au-ree:"):
        raise ValueError("Expected a versioned project-local ontology namespace")
    seen = set()
    for mapping in vocabulary.get("mappings", []):
        if (not all(isinstance(mapping.get(k), str) and mapping[k].strip()
                    for k in ("dimension", "label", "concept", "basis"))
                or mapping.get("relation") not in {"exactMatch", "closeMatch", "broadMatch", "relatedMatch"}):
            raise ValueError("Mappings require dimension, label, concept, relation and documented basis")
        key = (mapping["dimension"], _label(mapping["label"]))
        if key in seen:
            raise ValueError("Duplicate or ambiguous vocabulary mapping: " + repr(key))
        seen.add(key)
    # This profile uses direct mappings; chains need a separately reviewed policy.
    for mapping in vocabulary.get("mappings", []):
        if (mapping["dimension"], _label(mapping["concept"])) in seen:
            raise ValueError("Mapping chains are not allowed in this profile")
    return vocabulary


def normalize_context(context, vocabulary):
    if not isinstance(context, dict):
        raise ValueError("Context must be a mapping")
    mappings = {(m["dimension"], _label(m["label"])): m for m in vocabulary.get("mappings", [])}
    normalized, trace, uncertain = {}, [], []
    for dimension, value in sorted(context.items()):
        if not re.fullmatch(r"[a-z][a-z0-9_]*", dimension):
            raise ValueError("Invalid context dimension: " + str(dimension))
        if value is None or (isinstance(value, str) and not value.strip()):
            normalized[dimension] = None
            continue
        if not isinstance(value, (str, bool, int, float)) or (isinstance(value, (int, float)) and not math.isfinite(value)):
            raise ValueError("Context values must be scalar concepts/numbers or null")
        cleaned = _label(value) if isinstance(value, str) else value
        mapping = mappings.get((dimension, cleaned)) if isinstance(cleaned, str) else None
        if mapping and mapping["relation"] != "exactMatch":
            normalized[dimension] = None
            uncertain.append({"dimension": dimension, "label": value, **mapping})
        else:
            normalized[dimension] = mapping["concept"] if mapping else cleaned
            if mapping or cleaned != value:
                trace.append({"dimension": dimension, "original": value,
                              "canonical": normalized[dimension],
                              "rule": "DOCUMENTED_EXACT_LABEL" if mapping else "UNICODE_AND_WHITESPACE_ONLY"})
    return {"context": normalized, "mappings": trace, "unresolved_mappings": uncertain}


def _dependencies():
    try:
        from rdflib import Graph, Literal, Namespace, URIRef
        from pyshacl import validate
    except ImportError as exc:
        raise ImportError("Ontology experiments require pip install '.[ontology]'") from exc
    return Graph, Literal, Namespace, URIRef, validate


def vocabulary_graph(vocabulary):
    Graph, Literal, Namespace, URIRef, _ = _dependencies()
    graph = Graph()
    ns = Namespace(vocabulary["namespace"])
    rdf = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
    skos = Namespace("http://www.w3.org/2004/02/skos/core#")
    for mapping in vocabulary.get("mappings", []):
        prefix = str(ns) + "concept/" + mapping["dimension"] + "/"
        origin = URIRef(prefix + quote(_label(mapping["label"]), safe=""))
        target = URIRef(prefix + quote(mapping["concept"], safe=""))
        graph.add((origin, rdf.type, skos.Concept))
        graph.add((origin, skos.prefLabel, Literal(mapping["label"])))
        graph.add((origin, skos[mapping["relation"]], target))
        graph.add((origin, skos.scopeNote, Literal(mapping["basis"])))
        graph.add((target, rdf.type, skos.Concept))
        graph.add((target, skos.notation, Literal(mapping["concept"])))
    return graph


def assess_context(observed_context, target_context, vocabulary, *, case_id="case", source_pages=()):
    """Validate one declared use with actual SHACL min/max count and hasValue.

    Expected labels, case names and review reason codes never enter the decision.
    Only explicit semantic assertions, reviewed mappings and the target contract
    are used. Missing or close/broad-only concepts remain insufficient evidence.
    """
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("A stable case_id is required")
    if not target_context:
        raise ValueError("An empty contract would give vacuous comparability")
    if any(not isinstance(p, str) or not re.fullmatch(r"[a-f0-9]{64}:[1-9][0-9]*", p) for p in source_pages):
        raise ValueError("Source locators require SHA256:physical_page")
    observed = normalize_context(observed_context, vocabulary)
    target = normalize_context(target_context, vocabulary)
    if any(v is None for v in target["context"].values()) or target["unresolved_mappings"]:
        raise ValueError("Target contract must use explicit, unambiguous concepts")
    Graph, Literal, Namespace, URIRef, validate = _dependencies()
    ns = Namespace(vocabulary["namespace"])
    rdf = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
    sh = Namespace("http://www.w3.org/ns/shacl#")
    prov = Namespace("http://www.w3.org/ns/prov#")
    data, shapes = Graph(), Graph()
    node = URIRef(str(ns) + "evidence/" + quote(case_id, safe=""))
    profile = URIRef(str(ns) + "profile/" + digest(target["context"]))
    shape = URIRef(str(profile) + "/shape/" + digest(case_id))
    data.add((node, rdf.type, ns.EvidenceContext))
    data.add((node, rdf.type, prov.Entity))
    data.add((node, ns.declaredUse, profile))
    data.add((node, ns.rawContext, Literal(canonical(observed_context))))
    for page in sorted(set(source_pages)):
        source = URIRef("urn:sha256:" + page.replace(":", ":page:"))
        data.add((node, prov.wasDerivedFrom, source))
        data.add((source, rdf.type, prov.Entity))
    shapes.add((shape, rdf.type, sh.NodeShape))
    shapes.add((shape, sh.targetNode, node))

    def term(dimension, value):
        return (URIRef(str(ns) + "concept/" + dimension + "/" + quote(value, safe=""))
                if isinstance(value, str) else Literal(value))

    for dimension, value in observed["context"].items():
        if value is not None:
            data.add((node, ns[dimension], term(dimension, value)))
    for dimension, value in target["context"].items():
        prop = URIRef(str(shape) + "/" + dimension)
        shapes.add((shape, sh.property, prop))
        shapes.add((prop, sh.path, ns[dimension]))
        shapes.add((prop, sh.minCount, Literal(1)))
        shapes.add((prop, sh.maxCount, Literal(1)))
        shapes.add((prop, sh.hasValue, term(dimension, value)))
        shapes.add((prop, sh.message, Literal("Required context: " + dimension)))
    conforms, validation, _ = validate(data, shacl_graph=shapes, inference="none",
                                      advanced=False, do_owl_imports=False, meta_shacl=False)
    issues = []
    for result in validation.subjects(rdf.type, sh.ValidationResult):
        path = validation.value(result, sh.resultPath)
        component = validation.value(result, sh.sourceConstraintComponent)
        issues.append({"dimension": str(path).removeprefix(str(ns)),
                       "constraint": str(component).split("#")[-1]})
    issues = sorted({(i["dimension"], i["constraint"]) for i in issues})
    missing = sorted(k for k in target["context"] if observed["context"].get(k) is None)
    mismatches = sorted(k for k, v in target["context"].items()
                        if observed["context"].get(k) is not None
                        and term(k, observed["context"][k]) != term(k, v))
    expected_conformance = not missing and not mismatches
    if bool(conforms) != expected_conformance:
        raise ValueError("SHACL and explicit contract results disagree")
    status = ("COMPATIBLE_FOR_DECLARED_USE" if conforms else
              "CONTEXT_MISMATCH" if mismatches else "INSUFFICIENT_CONTEXT")
    report = {"case_id": case_id, "status": status, "admissible": bool(conforms),
              "contract_sha256": digest(target["context"]), "missing_context": missing,
              "mismatched_context": mismatches, "mapping_trace": observed["mappings"],
              "unresolved_mappings": observed["unresolved_mappings"],
              "violations": [{"dimension": d, "constraint": c} for d, c in issues],
              "source_pages": sorted(set(source_pages)),
              "scope": "DECLARED_CONTEXT_ONLY_NOT_FULL_COMPARABILITY_OR_SOURCE_REVERIFICATION"}
    return {"assessment": report, "data_graph": data, "shapes_graph": shapes}


def stable_ntriples(graph):
    """Deterministic graph export; generated graphs use named nodes only."""
    if any(term.n3().startswith("_:") for triple in graph for term in triple):
        raise ValueError("Stable ontology exports require named nodes")
    return "\n".join(sorted(line for line in graph.serialize(format="nt").splitlines() if line)) + "\n"
