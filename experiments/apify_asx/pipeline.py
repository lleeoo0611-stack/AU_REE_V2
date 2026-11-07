"""Isolated Apify discovery and 52-column export; never writes formal inputs.

Run this file from any directory. Only --mode live calls a paid Actor.
Search hits and parser candidates never become resource estimates implicitly.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timezone, timedelta
from urllib.parse import urlencode, urlsplit, urlunsplit, urldefrag
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from au_ree_v2.store import canonical, digest, filehash
from au_ree_v2.security import sensitive_reference, public_export
from au_ree_v2.pdf_extract import (recognize_document, project_registry,
                                    candidate_value_issues, DOCUMENT_VERSION)

HERE = Path(__file__).resolve().parent
BASE_COMMIT = 'b5e2a73438e2f3aa9f4adc3ab0f6ff0f898f0fca'


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def archive(work, raw, suffix):
    sha = hashlib.sha256(raw).hexdigest()
    path = Path(work) / 'captures' / (sha + suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and filehash(path) != sha:
        raise ValueError('IMMUTABLE_CAPTURE_MISMATCH')
    if not path.exists():
        path.write_bytes(raw)
    return sha, path


def load_baseline():
    data = json.loads((HERE / 'baseline_master.json').read_text(encoding='utf-8'))
    if data['baseline_sql_reconstruction']['commit'] != BASE_COMMIT:
        raise ValueError('BASELINE_COMMIT_MISMATCH')
    frozen = ROOT / 'results/phase22-2026-11-06'
    with (frozen / 'canonical_membership.csv').open(encoding='utf-8-sig') as stream:
        membership = list(csv.DictReader(stream))
    ids = {r['canonical_id'] for r in membership if r['kind'] == 'PROJECT'}
    if ids != {r[0] for r in data['rows']} or len(data['headers']) != 52:
        raise ValueError('BASELINE_MEMBERSHIP_MISMATCH')
    return data


def registry(baseline):
    """Aliases supply search/parser context only, with frozen canonical mapping."""
    frozen = ROOT / 'results/phase22-2026-11-06/canonical_membership.csv'
    with frozen.open(encoding='utf-8-sig') as stream:
        mapping = {r['entity_id']: r['canonical_id'] for r in csv.DictReader(stream)}
    groups = {r[0]: dict(entity_id=r[0], native_id=r[0], name=r[3], aliases={r[3]}, identity_source='PHASE22_CANONICAL_MEMBERSHIP') for r in baseline['rows']}
    for p in project_registry(ROOT):
        cid = mapping.get(p['entity_id'], p['entity_id'])
        if cid in groups:
            groups[cid]['aliases'].update(p['aliases'])
            groups[cid]['native_id'] = p['native_id']
    for row in baseline['review_rows']:
        groups[row[0]]['aliases'].update(x.strip() for x in row[-1].split(';') if x.strip())
    return [dict(p, aliases=sorted(p['aliases'])) for _, p in sorted(groups.items())]


def query_plan(config, projects, cutoff):
    after = ''  # Historical documents can contain the first usable resource.
    before = (date.fromisoformat(cutoff) + timedelta(days=1)).isoformat()
    jobs = []
    for q in config['global_queries']:
        jobs.append(dict(project_id=None, query=q + after + ' before:' + before, role='NATIONAL_DISCOVERY'))
    # Round-robin terms: truncation cannot spend the entire budget on one Project.
    for term in config['keywords']:
        for p in projects:
            alias = min(p['aliases'], key=lambda x: (len(x), x))
            alias = re.sub(r'["\r\n]', ' ', alias).strip()
            q = f'site:announcements.asx.com.au filetype:pdf "{alias}" "{term}" before:{before}'
            jobs.append(dict(project_id=p['entity_id'], query=q, role='REGISTERED_PROJECT_DISCOVERY'))
    for j in jobs:
        j['query_id'] = digest([config['version'], j])
    limit = int(config['max_queries'])
    if not 1 <= limit <= 1000:
        raise ValueError('INVALID_QUERY_LIMIT')
    offset = int(config.get('query_offset', 0))
    if not 0 <= offset < len(jobs):
        raise ValueError('INVALID_QUERY_OFFSET')
    chosen = jobs[offset:offset+limit]
    return dict(version=config['version'], cutoff=cutoff, jobs=chosen, query_offset=offset,
                planned_queries=len(chosen), all_available_queries=len(jobs),
                omitted_queries=len(jobs)-len(chosen), national_completeness=False)


def document_url(url, hosts):
    """Exact HTTPS origins only. Credential URLs, redirects and spoof hosts fail."""
    if not isinstance(url, str) or sensitive_reference(url):
        raise ValueError('UNSAFE_DOCUMENT_REFERENCE')
    p = urlsplit(url)
    if p.scheme != 'https' or p.hostname not in hosts or p.username or p.password or p.port not in (None, 443):
        raise ValueError('DOCUMENT_HOST_NOT_ALLOWED')
    return urldefrag(urlunsplit(('https', p.hostname, p.path, p.query, '')))[0]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ApifyClient:
    """No POST retry: an uncertain start must be reconciled, never billed twice."""
    def __init__(self, token, transport=None):
        if not token or not token.strip():
            raise ValueError('APIFY_TOKEN_MISSING')
        self.token = token.strip()
        self.transport = transport or self._http

    def _http(self, method, url, body, headers):
        request = Request(url, data=body, method=method, headers=headers)
        try:
            with build_opener(NoRedirect()).open(request, timeout=35) as response:
                raw = response.read(20000001)
                if len(raw) > 20000000:
                    raise ValueError('APIFY_RESPONSE_TOO_LARGE')
                return raw, dict(response.headers)
        except HTTPError as exc:
            raise RuntimeError('APIFY_HTTP_' + str(exc.code)) from None
        except (URLError, TimeoutError):
            raise RuntimeError('APIFY_NETWORK_OUTCOME_UNKNOWN_RESUME_EXISTING_RUN') from None

    def call(self, method, route, params=None, data=None):
        if not re.fullmatch(r'/[A-Za-z0-9_~/-]+', route):
            raise ValueError('INVALID_API_ROUTE')
        url = 'https://api.apify.com/v2' + route
        if params:
            url += '?' + urlencode(params)
        body = canonical(data).encode() if data is not None else None
        raw, headers = self.transport(method, url, body, {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        return json.loads(raw), headers

    def search(self, config, plan, work, resume_run=None):
        request_input = {'queries': '\n'.join(j['query'] for j in plan['jobs']),
                         'maxPagesPerQuery': config['max_pages_per_query'],
                         'countryCode': 'au', 'languageCode': 'en'}
        write_json(Path(work) / 'actor_input.json', request_input)
        if resume_run:
            run = self.call('GET', '/actor-runs/' + resume_run)[0]['data']
        else:
            # Persist intent before the paid request. Re-running a work directory
            # after an ambiguous failure requires --resume-run or a new directory.
            intent = Path(work) / 'start_intent.json'
            if intent.exists():
                raise ValueError('RUN_ALREADY_REQUESTED_USE_RESUME_RUN_OR_NEW_WORK')
            write_json(intent, {'input_sha256': digest(request_input), 'status': 'START_REQUESTED'})
            run = self.call('POST', '/acts/' + config['actor'] + '/runs',
                            {'timeout': config['actor_timeout_seconds'], 'maxTotalChargeUsd': config['max_total_charge_usd']}, request_input)[0]['data']
        fields = ('id', 'status', 'defaultDatasetId', 'buildId', 'buildNumber', 'startedAt', 'finishedAt', 'usageTotalUsd')
        write_json(Path(work) / 'apify_run.json', {k: run.get(k) for k in fields})
        deadline = time.monotonic() + config['actor_timeout_seconds'] + 60
        while run['status'] in ('READY', 'RUNNING', 'TIMING-OUT', 'ABORTING'):
            if time.monotonic() >= deadline:
                raise RuntimeError('ACTOR_WAIT_EXPIRED_RESUME_EXISTING_RUN')
            time.sleep(min(10, config['poll_seconds']))
            run = self.call('GET', '/actor-runs/' + run['id'])[0]['data']
            write_json(Path(work) / 'apify_run.json', {k: run.get(k) for k in fields})
        if run['status'] != 'SUCCEEDED':
            raise RuntimeError('APIFY_RUN_' + run['status'])
        rows, total, offset, receipts = [], None, 0, []
        while True:
            page, headers = self.call('GET', '/datasets/' + run['defaultDatasetId'] + '/items',
                                      {'format': 'json', 'clean': 'false', 'offset': offset, 'limit': config['dataset_page_size']})
            headers = {k.lower(): v for k, v in headers.items()}
            current = int(headers['x-apify-pagination-total'])
            if not isinstance(page, list) or (total is not None and current != total):
                raise ValueError('DATASET_PAGINATION_CONTRACT_CHANGED')
            total = current
            if total > config['max_dataset_items']:
                raise ValueError('DATASET_ITEM_BUDGET_EXCEEDED')
            if int(headers['x-apify-pagination-offset']) != offset or int(headers['x-apify-pagination-count']) != len(page):
                raise ValueError('DATASET_OFFSET_OR_COUNT_MISMATCH')
            safe = public_export(page)
            safe_sha, _ = archive(work, (canonical(safe) + '\n').encode(), '.serp.json')
            receipts.append(dict(offset=offset, count=len(page), total=total,
                                 original_canonical_json_sha256=digest(page),
                                 retained_sha256=safe_sha, credential_redaction_applied=page != safe))
            write_json(Path(work) / 'serp_receipts.json', receipts)
            rows.extend(safe)
            offset += len(page)
            if offset == total:
                break
            if not page or offset > total:
                raise ValueError('DATASET_TRUNCATED_OR_DUPLICATED')
        return rows


def flatten_results(dataset, plan, config):
    """SERP query association is retained, never used as Project attribution."""
    jobs = {j['query']: j for j in plan['jobs']}
    found = {}
    for page in dataset:
        q = page.get('searchQuery', {})
        q = q.get('term') or q.get('query') if isinstance(q, dict) else q
        for result in page.get('organicResults', []):
            try:
                url = document_url(result.get('url'), config['allowed_document_hosts'])
            except (ValueError, TypeError):
                continue
            # ASX PDF announcement paths can lack a .pdf extension.
            if not (urlsplit(url).path.lower().endswith('.pdf') or '/asxpdf/' in url.lower()):
                continue
            row = found.setdefault(url, dict(url=url, title=result.get('title', ''), description=result.get('description', ''), query_ids=[], search_project_ids=[], status='DISCOVERED_NOT_VERIFIED'))
            job = jobs.get(q)
            if job and job['query_id'] not in row['query_ids']:
                row['query_ids'].append(job['query_id'])
            if job and job['project_id'] and job['project_id'] not in row['search_project_ids']:
                row['search_project_ids'].append(job['project_id'])
    return [found[k] for k in sorted(found)]


def fetch_pdf(url, config):
    url = document_url(url, config['allowed_document_hosts'])
    request = Request(url, headers={'User-Agent': 'AU_REE_V2 research Apify experiment/1.0'})
    # No authenticated headers are ever sent to document origins.
    with build_opener(NoRedirect()).open(request, timeout=35) as response:
        raw = response.read(config['max_pdf_bytes'] + 1)
    if len(raw) > config['max_pdf_bytes']:
        raise ValueError('PDF_BYTE_BUDGET_EXCEEDED')
    if not raw.startswith(b'%PDF'):
        raise ValueError('NOT_A_PDF')
    return raw


def stage_documents(work, hits, config, projects, fetch=fetch_pdf):
    work = Path(work)
    # This schema contains experimental candidates only, no formal observations.
    db = sqlite3.connect(work / 'staging.sqlite')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS documents(source_sha TEXT PRIMARY KEY,url TEXT NOT NULL,raw TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS candidates(candidate_id TEXT PRIMARY KEY,source_sha TEXT NOT NULL,raw TEXT NOT NULL);
    ''')
    known = {s['sha256'] for s in json.loads((ROOT / 'data/manifest.json').read_text())['snapshots'] if s['kind'] == 'pdf'}
    all_candidates, documents, seen = {}, [], set()
    try:
        for hit in hits[:config['max_documents']]:
            row = dict(hit)
            try:
                raw = fetch(row['url'], config)
                if not raw.startswith(b'%PDF') or len(raw) > config['max_pdf_bytes']:
                    raise ValueError('PDF_CONTRACT_FAILED')
                sha, path = archive(work, raw, '.pdf')
                row.update(source_sha256=sha, bytes=len(raw), known_baseline_sha=sha in known,
                           raw_path=str(path.relative_to(work)), acquired_at=datetime.now(timezone.utc).isoformat())
                if sha in seen:
                    row['status'] = 'DUPLICATE_CONTENT'
                    documents.append(row)
                    continue
                seen.add(sha)
                source = dict(key='apify_asx_' + sha[:20], kind='pdf', url=row['url'],
                              path=str(path), sha256=sha)
                # Existing parser reads existing claims, without updating them.
                extracted = recognize_document(ROOT, source, projects)
                extracted = public_export(extracted)
                ex_sha, ex_path = archive(work, (canonical(extracted) + '\n').encode(), '.extraction.json')
                row.update(status='EXTRACTED_REVIEW_REQUIRED', publication_date=extracted.get('publication_date'),
                           extraction_sha256=ex_sha, extraction_path=str(ex_path.relative_to(work)),
                           pages=len(extracted['pages']), candidates=len(extracted['candidates']),
                           labels=extracted['mentioned_labels'])
                # Relative paths keep retained captures portable for replay.
                for c in extracted['candidates']:
                    c = dict(c, source_url=row['url'], retained_pdf=row['raw_path'],
                             retained_extraction=row['extraction_path'], extraction_sha256=ex_sha,
                             document_publication_date=extracted.get('publication_date'))
                    all_candidates[c['candidate_id']] = c
                    db.execute('INSERT OR REPLACE INTO candidates VALUES(?,?,?)', (c['candidate_id'], sha, canonical(c)))
                db.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?)', (sha, row['url'], canonical(row)))
            except Exception as exc:
                # Exception text can contain URL credentials; publish type/code only.
                row.update(status='FETCH_OR_EXTRACTION_FAILED', error=type(exc).__name__, http_status=getattr(exc, 'code', None))
            documents.append(row)
        db.commit()
    finally:
        db.close()
    return documents, all_candidates


def apply_decisions(data, candidates, decisions, work, cutoff):
    """Explicit source/scope verification authorizes a resource-only replacement.

    Resource replacement clears all old dependent composition quantities. The
    raw row and superseded provenance remain in the pinned baseline artifact.
    """
    rows = {r[0]: r for r in data['rows']}
    applied, used = [], set()
    for d in decisions:
        c = candidates[d['candidate_id']]
        pid = d['project_id']
        if pid not in rows or pid in used or c.get('project_id') != pid:
            raise ValueError('DECISION_PROJECT_AMBIGUOUS_OR_DUPLICATED')
        if c['kind'] != 'RESOURCE_TABLE_TOTAL' or c.get('issues') or candidate_value_issues(c):
            raise ValueError('RESOURCE_CANDIDATE_NOT_VALIDATED')
        if d.get('decision') != 'VERIFIED_REPLACE_RESOURCE' or not d.get('reviewer') or not d.get('reason') or not d.get('supersedes_same_scope'):
            raise ValueError('RESOURCE_SCOPE_REVIEW_REQUIRED')
        if c.get('resource_type') != 'MINERAL_RESOURCE' or c['basis'] != 'TREO' or not c.get('category') or 'TOTAL' not in c['category']:
            raise ValueError('RESOURCE_TOTAL_OR_BASIS_UNRESOLVED')
        if d.get('scope') != c['scope'] or d.get('source_sha256') != c['source_sha256']:
            raise ValueError('RESOURCE_SCOPE_OR_SOURCE_MISMATCH')
        effective = date.fromisoformat(d['effective_date']).isoformat()
        publication = c.get('publication_date') or c.get('document_publication_date')
        if effective > cutoff or not publication or publication > cutoff or effective > publication:
            raise ValueError('DATE_MISSING_OR_AFTER_CUTOFF')
        # The reviewer cites physical pages and literal markers for the effective
        # date and the replacement scope; publication date is never substituted.
        import pymupdf
        pdf_path = Path(work) / c['retained_pdf']
        if filehash(pdf_path) != c['source_sha256']:
            raise ValueError('RETAINED_SOURCE_HASH_MISMATCH')
        artifact_path = Path(work) / c['retained_extraction']
        if filehash(artifact_path) != c['extraction_sha256']:
            raise ValueError('RETAINED_EXTRACTION_HASH_MISMATCH')
        artifact = json.loads(artifact_path.read_text())
        if c.get('document_publication_date') and c['document_publication_date'] != artifact.get('publication_date'):
            raise ValueError('DOCUMENT_PUBLICATION_DATE_ARTIFACT_MISMATCH')
        source_candidate = next((x for x in artifact['candidates'] if x['candidate_id'] == c['candidate_id']), None)
        if source_candidate is None or any(c.get(k) != v for k, v in source_candidate.items()):
            raise ValueError('DECISION_CANDIDATE_ARTIFACT_MISMATCH')
        with pymupdf.open(pdf_path) as pdf:
            if not d.get('evidence') or not {'effective_date', 'same_scope_replacement'} <= {e['role'] for e in d['evidence']}:
                raise ValueError('RESOURCE_DATE_AND_SCOPE_EVIDENCE_REQUIRED')
            for evidence in d['evidence']:
                text = ' '.join(pdf[int(evidence['physical_page']) - 1].get_text(sort=True).split())
                if int(evidence['physical_page']) < 1 or not evidence['marker'].strip() or ' '.join(evidence['marker'].split()) not in text:
                    raise ValueError('DECISION_PAGE_MARKER_MISMATCH')
        units, values = c['units'], c['values']
        if units['ore_mt'] != 'Mt' or units['grade'] not in ('%', 'ppm'):
            raise ValueError('RESOURCE_UNIT_UNRESOLVED')
        ore, grade = values['ore_mt'], values['grade'] / (10000 if units['grade'] == 'ppm' else 1)
        treo = values.get('contained_treo_kt')
        calculated = ore * grade * 10
        if treo is None:
            treo = calculated
        if not all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0 for x in (ore, grade, treo)) or grade > 100:
            raise ValueError('RESOURCE_NUMERIC_CONTRACT_FAILED')
        if abs(treo - calculated) > .005 * max(treo, calculated):
            raise ValueError('RESOURCE_ARITHMETIC_CONFLICT')
        r = rows[pid]
        r[15:18] = [ore, grade, treo]
        for index in [18, 19, 20, 21, 36, *range(37, 52)]:
            r[index] = ''
        r[26:30] = ['是', '是', 'Apify發現之ASX原始文件（人工核對資源）', c['source_url']]
        r[30:36] = [0, '', '', '無法判定', '否', '']
        for review in data['review_rows']:
            if review[0] == pid:
                review[2:9] = ['已選核對資源', effective, c['scope'], c['basis'], pid, c['candidate_id'], '']
                review[9] = '新資源已取代先前選值；舊配分清空，待同範圍資料。'
        data['evidence_rows'] = [e for e in data['evidence_rows'] if e[0] != pid or not any(t in e[2] for t in ('蘊藏量', '品位', '磁鐵', '元素', '氧化'))]
        data['evidence_rows'].append([pid, r[3], '礦石蘊藏量_Mt／TREO品位_pct／總TREO蘊藏量_kt', canonical(values), '原件人工核對', c['source_key'], publication, effective, 'physical page ' + str(c['physical_page']), c['scope'], 'TREO_kt = ore_Mt × grade_pct × 10；舊配分清空', '', c['source_url'], c['source_sha256'], d['reason']])
        applied.append(d)
        used.add(pid)
    return applied


def export_master(data, out, summary, documents):
    """Exact header order and numeric CSV; workbook formulas match CSV values."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stem = 'AU_REE_Project_Master_Apify_Test_' + summary['export_date'].replace('-', '')
    with (out / (stem + '.csv')).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(data['headers'])
        writer.writerows([[format(v, '.15g') if isinstance(v, float) else v for v in r] for r in data['rows']])
    wb = Workbook()
    wb.remove(wb.active)
    sheets = [('專案總表', data['headers'], data['rows']),
              ('資源範圍與檢核', data['review_headers'], data['review_rows']),
              ('逐欄來源', data['evidence_headers'], data['evidence_rows']),
              ('欄位與版本說明', ['項目', '內容'],
               [[k, v] for k, v in {**data['metadata'], **summary}.items()] +
               [[], data['definition_headers'], *data['definition_rows']]),
              ('ASX文件搜尋', ['URL', '狀態', '文件SHA256', '已存於基線', '發布日期', '頁數', '候選數'],
               [[d.get(k, '') for k in ('url', 'status', 'source_sha256', 'known_baseline_sha', 'publication_date', 'pages', 'candidates')] for d in documents])]
    for name, headers, rows in sheets:
        ws = wb.create_sheet(name)
        ws.append(headers)
        for row in rows:
            ws.append([canonical(v) if isinstance(v, (dict, list)) else v for v in row])
        ws.freeze_panes = 'E2' if name == '專案總表' else 'B2'
        ws.sheet_view.showGridLines = False
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.fill = PatternFill('solid', fgColor='24435B')
            cell.font = Font(name='Arial', bold=True, color='FFFFFF', size=10)
            cell.alignment = Alignment(wrap_text=True, vertical='center')
        ws.row_dimensions[1].height = 44
        for col in range(1, ws.max_column + 1):
            ws.column_dimensions[get_column_letter(col)].width = 22
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.font = Font(name='Arial', size=10)
                cell.alignment = Alignment(vertical='center')
                if isinstance(cell.value, float):
                    cell.number_format = '0.0000'
                # Literal source strings must never execute as Excel formulas.
                if isinstance(cell.value, str) and cell.value.startswith(('=', '+', '-', '@')):
                    cell.data_type = 's'
        if name in ('逐欄來源', '資源範圍與檢核'):
            ws.column_dimensions['B'].width = 45
        if name == '欄位與版本說明':
            ws.column_dimensions['A'].width = 30
            ws.column_dimensions['B'].width = 115
            ws.column_dimensions['C'].width = 25
            ws.column_dimensions['D'].width = 70
            ws.column_dimensions['E'].width = 100
            for row in ws.iter_rows(min_row=2):
                row[1].alignment = Alignment(wrap_text=True, vertical='top')
                ws.row_dimensions[row[0].row].height = max(30, 15 * (len(str(row[1].value)) // 85 + 1))
            for row in ws.iter_rows(min_row=2):
                if row[0].value == '欄序':
                    for cell in row:
                        cell.fill = PatternFill('solid', fgColor='24435B')
                        cell.font = Font(name='Arial', bold=True, color='FFFFFF', size=10)
        if name == 'ASX文件搜尋':
            ws.column_dimensions['A'].width = 80
            ws.column_dimensions['B'].width = 38
    ws = wb['專案總表']
    ws.column_dimensions['D'].width = 48
    for i in range(2, len(data['rows']) + 2):
        for column, formula in {
            'U': f'=IF(COUNT(AN{i}:AO{i})=2,SUM(AN{i}:AO{i}),"")',
            'V': f'=IF(COUNT(AS{i}:AZ{i})=8,SUM(AS{i}:AZ{i}),"")',
            'AE': f'=COUNT(AL{i}:AZ{i})',
            'AF': f'=IF(AE{i}>0,SUM(AL{i}:AZ{i}),"")',
            'AG': f'=IF(AND(ISNUMBER(AF{i}),ISNUMBER(R{i}),R{i}>0),AF{i}/R{i},"")',
            'AH': f'=IF(ISNUMBER(AG{i}),IF(AF{i}>R{i}*1.005,"元素總量超出TREO","未見超量"),"無法判定")',
            'AI': f'=IF(COUNT(AN{i}:AO{i},AS{i}:AT{i})=4,"是","否")',
            'AJ': f'=IF(COUNT(AN{i}:AO{i},AS{i}:AT{i})=4,SUM(AN{i}:AO{i},AS{i}:AT{i}),"")'
        }.items():
            ws[f'{column}{i}'] = formula
    path = out / (stem + '.xlsx')
    wb.save(path)
    write_json(out / 'master_data.json', data)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['plan', 'replay', 'live'], default='plan')
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--as-of', default=date.today().isoformat())
    parser.add_argument('--dataset', type=Path)
    parser.add_argument('--pdf-index', type=Path, help='Offline replay URL-to-PDF-path JSON; paths relative to index')
    parser.add_argument('--decisions', type=Path)
    parser.add_argument('--resume-run')
    parser.add_argument('--max-queries', type=int)
    parser.add_argument('--query-offset', type=int, default=0)
    parser.add_argument('--max-documents', type=int)
    args = parser.parse_args(argv)
    date.fromisoformat(args.as_of)
    if args.as_of < '2026-11-05':
        raise ValueError('AS_OF_PRECEDES_FROZEN_BASELINE')
    work = args.work.resolve()
    # Work output may never target the repository's formal input/result paths.
    if work == ROOT or any(work.is_relative_to(ROOT / p) for p in ('src', 'config', 'data', 'results', 'experiments', '.git')):
        raise ValueError('WORK_MUST_BE_ISOLATED_FROM_FORMAL_INPUTS')
    work.mkdir(parents=True, exist_ok=True)
    config = json.loads((HERE / 'config.json').read_text())
    if args.max_queries is not None:
        config['max_queries'] = args.max_queries
    config['query_offset'] = args.query_offset
    if args.max_documents is not None:
        if not 1 <= args.max_documents <= 1000:
            raise ValueError('INVALID_DOCUMENT_LIMIT')
        config['max_documents'] = args.max_documents
    baseline = load_baseline()
    projects = registry(baseline)
    plan = query_plan(config, projects, args.as_of)
    write_json(work / 'query_plan.json', plan)
    write_json(work / 'config.json', config)
    before = {p: filehash(ROOT / p) for p in ('data/manifest.json', 'data/claims.json', 'config/research.json', 'config/sources.json')}
    summary = dict(mode=args.mode, status='PLANNED_NO_LIVE_SEARCH', export_date=args.as_of,
                   baseline_cutoff='2026-11-05', base_commit=BASE_COMMIT,
                   baseline_sha256=filehash(HERE / 'baseline_master.json'), planned_queries=plan['planned_queries'],
                   experiment_code_sha256=filehash(Path(__file__)), config_sha256=digest(config),
                   projects=len(baseline['rows']), columns=52, search_results=0, documents_fetched=0,
                   new_document_sha256=0, parsed_candidates=0, resource_updates=0,
                   new_mcda_eligible_projects=0, live_api_verified=False)
    hits, documents, candidates, error = [], [], {}, None
    try:
        if args.mode == 'live':
            client = ApifyClient(os.environ.get('APIFY_TOKEN'))
            dataset = client.search(config, plan, work, args.resume_run)
            summary['live_api_verified'] = True
        elif args.mode == 'replay':
            if args.dataset is None:
                raise ValueError('REPLAY_DATASET_REQUIRED')
            dataset = json.loads(args.dataset.read_text(encoding='utf-8'))
        else:
            dataset = None
        if dataset is not None:
            if not isinstance(dataset, list):
                raise ValueError('DATASET_MUST_BE_SERP_PAGE_ARRAY')
            safe = public_export(dataset)
            summary['dataset_sha256'], _ = archive(work, (canonical(safe) + '\n').encode(), '.serp.json')
            hits = flatten_results(safe, plan, config)
            fetch = fetch_pdf
            if args.mode == 'replay':
                if args.pdf_index is None and hits:
                    raise ValueError('REPLAY_PDF_INDEX_REQUIRED_NO_NETWORK_ALLOWED')
                index = json.loads(args.pdf_index.read_text()) if args.pdf_index else {}
                def fetch(url, settings):
                    if url not in index:
                        raise ValueError('REPLAY_PDF_NOT_RETAINED')
                    return (args.pdf_index.parent / index[url]).read_bytes()
            documents, candidates = stage_documents(work, hits, config, projects, fetch=fetch)
            summary.update(status='SEARCH_PROCESSED_REVIEW_REQUIRED', search_results=len(hits),
                           documents_fetched=sum(bool(d.get('source_sha256')) for d in documents),
                           new_document_sha256=len({d['source_sha256'] for d in documents if d.get('source_sha256') and not d.get('known_baseline_sha')}),
                           parsed_candidates=len(candidates), document_budget_deferred=max(0, len(hits)-config['max_documents']))
        data = copy.deepcopy(baseline)
        if args.decisions:
            decisions = json.loads(args.decisions.read_text(encoding='utf-8'))
            applied = apply_decisions(data, candidates, decisions, work, args.as_of)
            summary['resource_updates'] = len(applied)
            summary['decisions_sha256'] = filehash(args.decisions)
            write_json(work / 'applied_decisions.json', applied)
    except Exception as exc:
        data = copy.deepcopy(baseline)
        error = str(exc) if re.fullmatch('[A-Z0-9_]+', str(exc)) else type(exc).__name__
        summary.update(status='BLOCKED_' + error, resource_updates=0)
    finally:
        after = {p: filehash(ROOT / p) for p in before}
        summary['formal_input_hashes_unchanged'] = before == after
        summary['formal_input_hashes'] = after
        if before != after:
            raise ValueError('FORMAL_INPUTS_CHANGED')
    summary['master_values'] = 'BASELINE_ONLY' if not summary['resource_updates'] else 'BASELINE_WITH_REVIEWED_RESOURCE_UPDATES'
    data['metadata'].update({'本次搜尋狀態': summary['status'], '本次新增資源': summary['resource_updates'],
                             '本次總表': summary['master_values'], '製表日期': args.as_of,
                             '本次取值方式': '讀取先前SQLite匯出總表之凍結衍生快照；本次未重查正式SQL。新資源僅經來源核對與scope替換decision後納入。'})
    write_json(work / 'document_inventory.json', documents)
    write_json(work / 'candidate_review.json', list(candidates.values()))
    write_json(work / 'search_results.json', hits)
    export_master(data, work / 'outputs', summary, documents)
    summary['outputs'] = {p.name: filehash(p) for p in sorted((work / 'outputs').glob('*')) if p.is_file()}
    write_json(work / 'run_summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 2 if error else 0


if __name__ == '__main__':
    raise SystemExit(main())
