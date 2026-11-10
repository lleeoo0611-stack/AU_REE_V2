"""Scoped user-provided vocabulary projection; independent of DRAFT approval."""
import csv
import json
from pathlib import Path
from .store import canonical, filehash
from .classification import FIELDS


def load_template_mapping(path):
    path = Path(path)
    cfg = json.loads(path.read_text(encoding='utf-8'))
    if cfg.get('version') != 'user-template-mapping-v1' or cfg.get('status') != 'USER_PROVIDED_SCOPED_MAPPING':
        raise ValueError('TEMPLATE_MAPPING_VERSION_OR_STATUS')
    source = cfg['source']
    raw = (path.parent.parent / source['local_path']).resolve()
    if filehash(raw) != source['sha256'] or raw.stat().st_size != source['bytes']:
        raise ValueError('TEMPLATE_MAPPING_SOURCE_HASH')
    with raw.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    if len(rows) != source['rows'] or len(rows[0]) != source['columns']:
        raise ValueError('TEMPLATE_MAPPING_SOURCE_SHAPE')
    for group, (native, targets) in FIELDS.items():
        for text, entry in cfg['mappings'][group].items():
            if not text or not entry.get('rationale'):
                raise ValueError('TEMPLATE_MAPPING_RATIONALE')
            # Every output tuple must occur together in the original CSV.
            if not any(all(r[column] == entry[key] for key, column in targets.items()) and
                       r[native] == entry['template_label'] for r in rows):
                raise ValueError('TEMPLATE_MAPPING_TUPLE_NOT_IN_SOURCE')
    return dict(config=cfg, sha256=filehash(path))


def template_mapping_fills(row, provenance, book):
    cfg = book['config']; result = []
    for group, (source, targets) in FIELDS.items():
        entry = cfg['mappings'][group].get(row.get(source, ''))
        if entry is None:
            continue
        native = next((p for p in provenance if p['project_id'] == row['專案ID'] and p['column'] == source), None)
        if native is None:
            raise ValueError('TEMPLATE_MAPPING_NATIVE_PROVENANCE_REQUIRED')
        for key, column in targets.items():
            if row[column] != '':
                continue
            result.append(dict(column=column, value=entry[key], sha=native['source_sha256'],
                locator='user CSV vocabulary; exact dated native description from '+source,
                method='USER_PROVIDED_TEMPLATE_MAPPING_FROM_'+source,
                scope=canonical(dict(mapping_version=cfg['version'], mapping_sha256=book['sha256'],
                    vocabulary_source_sha256=cfg['source']['sha256'], source_column=source,
                    source_value=row[source], source_provenance=native, template_label=entry['template_label'],
                    rationale=entry['rationale'], temporal_scope='AT_NATIVE_SOURCE_DATE_NOT_CURRENT_STATUS',
                    codebook_approval='UNCHANGED_DRAFT;ONLY_THESE_EXPLICIT_MAPPINGS'))))
    return result
