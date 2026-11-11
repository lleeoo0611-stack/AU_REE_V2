"""Offline, fail-closed stage inference over all associated archived originals."""
import csv
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

RULE = 'STAGE_INFERRED_FROM_EVIDENCE_ABSENCE'
EVIDENCE = '甲1 甲2 刪掉 乙1 (a) 放寬條件、(c) Mt Stirling 共點、(d) VIC／TAS核准 乙2 可以，核准 乙5 第一個全產期'
DEFAULT_KEYWORDS = ['Scoping', 'PFS', 'DFS', 'BFS', 'Feasibility', 'FID', 'construction', 'production', 'withdraw']


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def date_known(value):
    if not isinstance(value, str):
        return False
    try:
        if re.fullmatch(r'\d{4}', value):
            date(int(value), 1, 1)
        elif re.fullmatch(r'\d{4}-\d{2}', value):
            date.fromisoformat(value + '-01')
        else:
            date.fromisoformat(value)
        return True
    except ValueError:
        return False


def original_inventory(repo, census_root, project_ids):
    """Union archived associations, including nonselected evidence; never name-match."""
    repo, census_root = Path(repo).resolve(), Path(census_root).resolve()
    cfg = read_json(repo / 'config/asx_local_asset_roots.json')
    roots = {k: (repo / v).resolve() for k, v in cfg['roots'].items()}
    roots['canonical'] = census_root
    sources = read_json(repo / 'config/asx_source_reviews.json')
    discovery = read_json(repo / 'config/asx_discovery_reviews.json')
    identity = read_json(repo / 'config/asx_project_identity_reviews.json')
    locations = read_json(repo / 'config/asx_location_reviews.json')
    mapping = {m['absorbed_id']: m['target_id'] for m in identity.get('merges', [])}
    database = census_root / 'work/phase22/verified-performance-v3/isolated-round-0/after/canonical.sqlite'
    db = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    for r in db.execute("SELECT parent_id, child_id FROM relations WHERE relation='DOCUMENT_SUPPORTED_SAME_PROJECT'"):
        if r['child_id'] in mapping and mapping[r['child_id']] != r['parent_id']:
            raise ValueError('STAGE_AMBIGUOUS_CANONICAL_MAPPING')
        mapping[r['child_id']] = r['parent_id']

    def canonical(pid):
        seen = set()
        while pid in mapping:
            if pid in seen:
                raise ValueError('STAGE_CYCLIC_CANONICAL_MAPPING')
            seen.add(pid)
            pid = mapping[pid]
        return pid

    inventories = {pid: {} for pid in project_ids}
    issues = defaultdict(list)

    def add(pid, source, root, origin, source_date=None):
        pid = canonical(pid)
        if pid not in inventories:
            return
        sha = source.get('source_sha256') or source.get('sha256') or source.get('sha')
        path = source.get('path')
        if not sha or not path or root is None:
            issues[pid].append(dict(reason='ARCHIVE_REFERENCE_INCOMPLETE', association=origin, sha256=sha or ''))
            return
        full = (Path(root) / path).resolve()
        # A ledger may name an absolute root, never an out-of-root original path.
        if not full.is_relative_to(Path(root).resolve()):
            issues[pid].append(dict(reason='ARCHIVE_PATH_OUTSIDE_ROOT', association=origin, sha256=sha))
            return
        value = dict(sha256=sha, path=str(full), kind=source.get('kind') or full.suffix.lstrip('.'),
                     url=source.get('url', ''), dates=[], associations=[])
        previous = inventories[pid].setdefault(sha, value)
        if str(full) not in previous.setdefault('paths', []):
            previous['paths'].append(str(full))
        for d in [source_date, source.get('publication_date'), source.get('document_issue_date')]:
            if date_known(d) and d not in previous['dates']:
                previous['dates'].append(d)
        if origin not in previous['associations']:
            previous['associations'].append(origin)

    stored = {r['sha']: dict(r) for r in db.execute('SELECT * FROM sources')}
    associations = set()
    for table, entity_column in [('records', 'entity_id'), ('observations', 'entity_id'), ('study_cases', 'project_id'), ('review_queue', 'entity_id')]:
        for r in db.execute(f'SELECT {entity_column}, source_sha FROM {table}'):
            if r[0] and r[1]:
                associations.add((r[0], r[1], 'census:' + table))
    for r in db.execute('SELECT parent_id,child_id,source_sha FROM relations'):
        # The relation source is documentary evidence about each named endpoint.
        for pid in [r[0], r[1]]:
            if pid and r[2]:
                associations.add((pid, r[2], 'census:relations'))
    for r in db.execute('SELECT selection_entity_id,parent_candidate_id,source_sha FROM census_screen_index'):
        for pid in [r[0], r[1]]:
            if pid and r[2]:
                associations.add((pid, r[2], 'census:screen_index'))
    for pid, sha, origin in sorted(associations):
        if canonical(pid) not in inventories:
            continue
        if sha not in stored:
            issues[canonical(pid)].append(dict(reason='CENSUS_SOURCE_MISSING', sha256=sha, association=origin))
            continue
        s = stored[sha]
        meta = json.loads(s.get('metadata') or '{}')
        add(pid, s, meta.get('asset_root') or census_root, origin)
    db.close()
    for review in sources.get('reviews', []):
        add(review['project_id'], review, roots.get(review.get('asset_set')), 'source-review:' + review['review_id'])
    from au_ree_v2.reviewed_discovery import project_id
    for entry in discovery.get('candidates', []):
        if entry.get('decision') != 'ADMIT_PROJECT':
            continue
        pid = project_id(entry['candidate_key'])
        ident = entry.get('identity', {})
        for index, source in enumerate(entry.get('sources', [])):
            source_date = ident.get('publication_date') if index == ident.get('source_index') else source.get('publication_date')
            bridge = ident.get('state_bridge', {})
            if index == bridge.get('source_index'):
                source_date = bridge.get('publication_date', source_date)
            add(pid, source, roots.get(source.get('asset_set')), 'discovery:' + entry['candidate_key'], source_date)
        bridge = ident.get('state_source_bridge') or entry.get('state_source_bridge')
        if isinstance(bridge, dict) and isinstance(bridge.get('source'), dict):
            source = bridge['source']
            add(pid, source, roots.get(source.get('asset_set')), 'discovery:state-bridge', bridge.get('publication_date'))
    for code in identity.get('codes', []):
        source = identity.get('sources', {}).get(code['source_key'])
        if source:
            add(code['project_id'], source, roots.get(source.get('asset_set')), 'identity:' + code['review_id'], code.get('evidence_date'))
        elif canonical(code['project_id']) in inventories:
            issues[canonical(code['project_id'])].append(dict(reason='IDENTITY_SOURCE_MISSING', association=code['source_key']))
    for review in locations.get('reviews', []):
        source = locations.get('sources', {}).get(review['source_key'])
        if source:
            add(review['project_id'], source, roots.get(source.get('asset_set')), 'location:' + review['review_id'], locations.get('effective_date'))
        elif canonical(review['project_id']) in inventories:
            issues[canonical(review['project_id'])].append(dict(reason='LOCATION_SOURCE_MISSING', association=review['source_key']))
    # Dates belong to original SHA, so a reviewed date can resolve the same
    # original's otherwise undated reference on a different association.
    sha_dates = defaultdict(set)
    for inventory in inventories.values():
        for sha, entry in inventory.items():
            sha_dates[sha].update(entry['dates'])
    for inventory in inventories.values():
        for sha, entry in inventory.items():
            entry['dates'] = sorted(sha_dates[sha])
            entry['associations'].sort()
            entry['paths'].sort()
    return {pid: [inventory[k] for k in sorted(inventory)] for pid, inventory in inventories.items()}, dict(issues)


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.text = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() in ('script', 'style'):
            self.depth += 1
    def handle_endtag(self, tag):
        if tag.lower() in ('script', 'style') and self.depth:
            self.depth -= 1
    def handle_data(self, data):
        if not self.depth:
            self.text.append(data)


def scan_original(entry, keywords):
    """Read every PDF physical page; missing/unextractable originals fail closed."""
    paths = entry.get('paths') or [entry['path']]
    existing = [Path(p) for p in paths if Path(p).is_file()]
    if not existing:
        return [], [dict(reason='ARCHIVED_ORIGINAL_MISSING', source_sha256=entry['sha256'])], 0
    path = existing[0]
    if sha256(path) != entry['sha256']:
        return [], [dict(reason='ARCHIVED_ORIGINAL_SHA_MISMATCH', source_sha256=entry['sha256'])], 0
    hits, problems = [], []
    pages = []
    kind = entry.get('kind', '').lower()
    try:
        if kind == 'pdf' or path.suffix.lower() == '.pdf':
            import fitz
            with fitz.open(path) as doc:
                if doc.needs_pass:
                    raise ValueError('ENCRYPTED_PDF')
                for index, page in enumerate(doc):
                    text = page.get_text(sort=True)
                    image_area = sum((rect & page.rect).get_area() for img in page.get_images(full=True) for rect in page.get_image_rects(img[0]))
                    if page.rect.get_area() and image_area / page.rect.get_area() >= 0.25:
                        problems.append(dict(reason='IMAGE_DOMINATED_PAGE_REQUIRES_OCR_REVIEW', physical_page=index + 1, source_sha256=entry['sha256'], image_area_fraction=round(image_area / page.rect.get_area(), 6)))
                    if not text.strip() or (page.get_images() and len(re.findall(r'[A-Za-z\u4e00-\u9fff]', text)) < 80):
                        problems.append(dict(reason='PAGE_WITHOUT_EXTRACTABLE_TEXT', physical_page=index + 1, source_sha256=entry['sha256']))
                    pages.append((index + 1, text))
        else:
            text = path.read_bytes().decode('utf-8-sig')
            if kind in ('html', 'htm') or path.suffix.lower() in ('.html', '.htm'):
                parser = VisibleHTML(); parser.feed(text); text = '\n'.join(parser.text)
            elif kind not in ('json', 'geojson', 'csv', 'txt', 'xml', 'text') and path.suffix.lower() not in ('.json', '.geojson', '.csv', '.txt', '.xml'):
                raise ValueError('UNSUPPORTED_ORIGINAL_FORMAT:' + kind)
            if not text.strip():
                raise ValueError('NO_EXTRACTABLE_TEXT')
            pages = [(None, text)]
    except Exception as exc:
        problems.append(dict(reason='ARCHIVED_ORIGINAL_UNREADABLE', source_sha256=entry['sha256'], detail=str(exc)))
    for page, text in pages:
        text = re.sub(r'(?<=\w)[-‐‑]\s*\n\s*(?=\w)', '', text)
        text = ' '.join(text.split())
        for keyword in keywords:
            # Case-insensitive literal stem catches withdrawals/production,
            # deliberate conservative whole-original search as authorized.
            pattern = r'\b' + re.escape(keyword)
            if keyword.upper() in ('PFS', 'DFS', 'BFS', 'FID'):
                pattern += r'\b'
            for match in re.finditer(pattern, text, re.I):
                hits.append(dict(source_sha256=entry['sha256'], physical_page=page,
                                 keyword=keyword, text=text[max(0, match.start()-120):match.end()+160]))
    return hits, problems, len(pages)


def verify_visual_reviews(entry, scan, proof, keywords, version):
    """Resolve only image/text extraction gaps using hash-bound full-page reviews."""
    hits, issues, pages = scan
    records = [r for r in proof.get('reviews', []) if r.get('source_sha256') == entry['sha256']]
    if not records:
        return hits, issues, pages, []
    import fitz
    expected = dict(engine='PyMuPDF', version=fitz.VersionBind, dpi=150,
                    colorspace='RGB', alpha=False, annots=True)
    if (proof.get('version') != 'round3-stage-visual-v1' or proof.get('keyword_version') != version
            or proof.get('keywords') != keywords or proof.get('renderer') != expected):
        raise ValueError('STAGE_VISUAL_RECIPE_OR_KEYWORDS_MISMATCH')
    paths = entry.get('paths') or [entry['path']]
    path = next((Path(p) for p in paths if Path(p).is_file()), None)
    if path is None or sha256(path) != entry['sha256']:
        raise ValueError('STAGE_VISUAL_ORIGINAL_SHA_MISMATCH')
    verified, seen, extra_hits = [], set(), []
    with fitz.open(path) as doc:
        for record in records:
            page = record.get('physical_page')
            if type(page) is not int or not 1 <= page <= len(doc) or page in seen:
                raise ValueError('STAGE_VISUAL_PAGE_INVALID_OR_DUPLICATE')
            seen.add(page)
            rendered = doc[page-1].get_pixmap(dpi=150, colorspace=fitz.csRGB, alpha=False, annots=True).tobytes('png')
            if hashlib.sha256(rendered).hexdigest() != record.get('render_sha256'):
                raise ValueError('STAGE_VISUAL_RENDER_SHA_MISMATCH')
            if record.get('coverage') != 'FULL_PAGE' or not record.get('visible_findings'):
                raise ValueError('STAGE_VISUAL_FULL_PAGE_FINDINGS_REQUIRED')
            outcome = record.get('outcome')
            found = record.get('hits')
            if outcome == 'NO_STAGE_KEYWORDS_VISIBLE' and found == []:
                pass
            elif outcome == 'STAGE_KEYWORDS_VISIBLE' and isinstance(found, list) and found:
                for hit in found:
                    if hit.get('keyword') not in keywords or not hit.get('text'):
                        raise ValueError('STAGE_VISUAL_HIT_INVALID')
                    extra_hits.append(dict(hit, source_sha256=entry['sha256'], physical_page=page, method='DIRECT_VISUAL_REVIEW'))
            else:
                raise ValueError('STAGE_VISUAL_OUTCOME_INVALID')
            verified.append(dict(record, renderer=expected, keyword_version=version))
    removable = {'IMAGE_DOMINATED_PAGE_REQUIRES_OCR_REVIEW', 'PAGE_WITHOUT_EXTRACTABLE_TEXT'}
    remaining = [i for i in issues if not (i.get('reason') in removable and i.get('physical_page') in seen)]
    return hits + extra_hits, remaining, pages, verified


def collect_stage_absence(rows, provenance, decisions, repo, census_root, settings):
    from au_ree_v2.stage_rules import selected_mre
    keywords = settings['keywords']
    version = settings['keyword_version']
    proof = read_json(Path(repo) / settings['visual_review_file']) if settings.get('visual_review_file') else {}
    if not keywords or not set(k.casefold() for k in DEFAULT_KEYWORDS) <= set(k.casefold() for k in keywords):
        raise ValueError('STAGE_REQUIRED_KEYWORDS_MISSING')
    approved = [d for d in decisions['decisions'] if d.get('decision_id') == settings['decision_id'] and d.get('rule') == RULE and d.get('decided_by') == 'USER_EXPLICIT_APPROVAL' and d.get('approval_evidence') == EVIDENCE]
    if len(approved) != 1:
        raise ValueError('STAGE_EXPLICIT_APPROVAL_REQUIRED')
    targets = [r for r in rows if not r.get('開發階段') and not r.get('開發階段代碼') and not r.get('開發階段類別')]
    inventories, inventory_issues = original_inventory(repo, census_root, {r['專案ID'] for r in targets})
    fills, reviews, manifests, cache = [], [], [], {}
    for row in targets:
        pid = row['專案ID']; originals = inventories[pid]
        problems = list(inventory_issues.get(pid, [])); hits = []
        if not originals:
            problems.append(dict(reason='NO_ASSOCIATED_ARCHIVED_ORIGINALS'))
        scanned = []
        for entry in originals:
            key = entry['sha256'], tuple(entry.get('paths', [entry['path']]))
            if key not in cache:
                cache[key] = verify_visual_reviews(entry, scan_original(entry, keywords), proof, keywords, version)
            found, issues, pages, visual = cache[key]
            hits.extend(found); problems.extend(issues)
            if not entry['dates']:
                problems.append(dict(reason='ARCHIVED_ORIGINAL_DATE_UNKNOWN', source_sha256=entry['sha256']))
            scanned.append(dict(source_sha256=entry['sha256'], source_url=entry['url'], dates=entry['dates'], associations=entry['associations'], physical_pages_scanned=pages, verified_visual_page_reviews=visual))
        has_mre, mre_evidence = selected_mre(row, provenance)
        if has_mre is None:
            problems.append(dict(reason='SELECTED_MRE_STATE_UNRESOLVED', detail=mre_evidence))
        manifest = dict(project_id=pid, project=row['專案名稱'], originals=scanned,
                        original_sha256s=sorted(e['sha256'] for e in originals), keywords=keywords,
                        keyword_version=version, hits=hits, blockers=problems,
                        latest_original_date=max((d for e in originals for d in e['dates']), default=None),
                        search_scope='ALL_ASSOCIATED_ARCHIVED_ORIGINALS_ALL_PHYSICAL_PAGES')
        manifests.append(manifest)
        if hits or problems:
            reviews.append(dict(project_id=pid, project=row['專案名稱'], reason='STAGE_KEYWORD_HIT' if hits else 'STAGE_SEARCH_INCOMPLETE', hits=hits, blockers=problems, original_sha256s=manifest['original_sha256s']))
            continue
        code = 'A2' if has_mre is True else 'A1'
        scope = dict(manifest, qualifier=RULE, decision_id=settings['decision_id'], selected_mre=has_mre,
                     interpretation='SOURCE_SET_AS_OF_DATE_INFERENCE_NOT_NATIVE_STAGE_STATEMENT_OR_CURRENT_STATUS')
        latest = max(originals, key=lambda e: (max(e['dates']), e['sha256']))
        locator = 'All associated originals and all physical pages; keyword list ' + version + '; as of ' + manifest['latest_original_date']
        for column, value in [('開發階段代碼', code), ('開發階段類別', '探勘')]:
            p = dict(project_id=pid, column=column, value=value, method=RULE, source_sha256=latest['sha256'],
                     source_url=latest['url'], publication_date=manifest['latest_original_date'], locator=locator,
                     scope=json.dumps(scope, ensure_ascii=False, sort_keys=True), observation_ids='[]',
                     review_ids=json.dumps([settings['decision_id']]), review_methods=json.dumps([RULE]),
                     source_kind='ARCHIVED_EVIDENCE_ABSENCE_INFERENCE')
            fills.append(dict(project_id=pid,column=column,value=value,method=RULE,decision_id=settings['decision_id'],provenance=p))
    return fills, reviews, dict(stage_search_manifests=manifests, scanned_projects=len(targets), network_requests=0)
