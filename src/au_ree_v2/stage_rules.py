"""Conservative, researcher-gated development-stage projection (offline only)."""
import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from .store import canonical

SCOPE = 'DATED_NATIVE_DEVELOPMENT_STAGE_AND_SELECTED_MRE_ONLY'
CATEGORIES = {'A1': '探勘', 'A2': '探勘', 'B1': '評估', 'B2': '評估', 'C1': '開發', 'C2': '開發'}
RULES = {
    'A1': 'EXPLORATION_WITHOUT_SELECTED_MRE',
    'A2': 'EXPLORATION_WITH_SELECTED_MRE',
    'B1': 'COMPLETED_SCOPING_OR_PFS',
    'B2': 'COMPLETED_DFS_BFS_OR_FEASIBILITY',
    'C1': 'ANNOUNCED_FINAL_INVESTMENT_DECISION',
    'C2': 'CONSTRUCTION_IN_PROGRESS',
}


def proposed_decisions():
    proposals = [dict(decision_id='stage-'+code.lower()+'-20261111', rule=rule,
                      scope=SCOPE, decided_by=None, decided_date='2026-11-11',
                      notes='僅依來源原文與既有 provenance；不回填既有值；不自動指派 A3。')
                 for code, rule in RULES.items()]
    for rule, notes in (
        ('IN_PROGRESS_STUDY_USE_HIGHEST_EXPLICIT_COMPLETED', '進行中的研究不算完成；上一階不明則待審。'),
        ('OPERATING_REQUIRES_DESIGN_CAPACITY_REVIEW', 'Operating／started production 不自動對照 D3。'),
        ('WITHDRAWAL_REQUIRES_RESEARCHER_REVIEW', '退出／中止不自動對照 X 類。')):
        proposals.append(dict(decision_id='stage-'+rule.lower()+'-20261111', rule=rule,
                              scope=SCOPE, decided_by=None, decided_date='2026-11-11', notes=notes))
    return proposals


def decision_records(decisions):
    if isinstance(decisions, (str, Path)):
        decisions = json.loads(Path(decisions).read_text(encoding='utf-8-sig'))
    records = decisions.get('decisions', []) if isinstance(decisions, dict) else decisions
    if not isinstance(records, list):
        raise ValueError('STAGE_DECISIONS_LIST_REQUIRED')
    return records


def approved_decision(decisions, rule):
    matches = [d for d in decision_records(decisions) if d.get('rule') == rule and d.get('scope') == SCOPE]
    if len(matches) > 1:
        raise ValueError('STAGE_DUPLICATE_RULE_DECISION')
    if not matches or not isinstance(matches[0].get('decided_by'), str) or not matches[0]['decided_by'].strip():
        return None
    d = matches[0]
    if not d.get('decision_id'):
        raise ValueError('STAGE_DECISION_ID_REQUIRED')
    try:
        date.fromisoformat(d['decided_date'])
    except (KeyError, TypeError, ValueError):
        raise ValueError('STAGE_DECISION_DATE_REQUIRED') from None
    return d


def _native(row, provenance, column):
    matches = [p for p in provenance if p.get('project_id') == row['專案ID'] and p.get('column') == column]
    if len(matches) != 1 or str(matches[0].get('value', '')) != str(row.get(column, '')) or not matches[0].get('source_sha256'):
        return None
    return matches[0]


def selected_mre(row, provenance):
    """No grade/TREO inference; a selected positive ore value needs its own trace."""
    column = '礦石蘊藏量_Mt'
    value = row.get(column, '')
    if value == '':
        if any(row.get(c, '') != '' for c in ('TREO品位_pct', '總TREO蘊藏量_kt')):
            return None, {'reason': 'INCONSISTENT_SELECTED_RESOURCE_FIELDS'}
        return False, {'column': column, 'value': '', 'reason': 'NO_SELECTED_RESOURCE_ORE_VALUE'}
    native = _native(row, provenance, column)
    try:
        positive = Decimal(str(value)).is_finite() and Decimal(str(value)) > 0
    except InvalidOperation:
        positive = False
    if native is None or not positive:
        return None, {'reason': 'SELECTED_MRE_PROVENANCE_REQUIRED'}
    return True, {'column': column, 'value': value, 'source_provenance': native}


def classify_stage(text, has_mre):
    """Return a proposal, never approval. Ambiguous completion stays in review."""
    text = (text or '').strip()
    result = {'source_text': text, 'code': None, 'category': None, 'rule': None, 'reason': ''}
    def finish(reason, code=None, ongoing=False):
        result.update(reason=reason, code=code, category=CATEGORIES.get(code), rule=RULES.get(code), ongoing_study=ongoing)
        return result
    if not text:
        return finish('NO_NATIVE_STAGE_TEXT')
    t = text.lower()
    if re.search(r'withdraw|\babandon|\bterminat|\bceased|\bsuspend|退出|中止|暫停', t):
        return finish('WITHDRAWAL_REQUIRES_RESEARCHER_REVIEW')
    if re.search(r'\boperating\b|started production|mining has now commenced|\bproducing\b|營運|開採中', t):
        return finish('OPERATING_NOT_EVIDENCE_OF_DESIGN_CAPACITY')
    if re.search(r'\bnot\b|\bno\b|未完成|尚未|取消|contradict|conflict', t):
        return finish('NEGATED_OR_CONTRADICTORY_STAGE_REQUIRES_REVIEW')
    future = r'\b(?:planned|planning|proposed|expected|anticipated|targeted|intended|will|would|could|may|might)\b|預計|計畫|擬議'
    if re.search(r'construction|建設|final investment decision|最終投資決定', t) and re.search(future, t):
        return finish('PLANNED_OR_CONDITIONAL_DEVELOPMENT_REQUIRES_REVIEW')
    if re.search(r'under construction|construction (?:is )?(?:underway|in progress)|建設中', t):
        return finish('EXPLICIT_CONSTRUCTION', 'C2')
    if re.search(r'(?:announced|made|taken|approved|reached).{0,30}final investment decision|final investment decision.{0,30}(?:announced|made|taken|approved|reached)|已公布最終投資決定', t):
        return finish('EXPLICIT_FINAL_INVESTMENT_DECISION', 'C1')
    study = re.compile(r'pre[ -]?feasibility(?: study)?|preliminary feasibility(?: study)?|\bpfs\b|definitive feasibility(?: study)?|bankable feasibility(?: study)?|\bdfs\b|\bbfs\b|feasibility study|scoping(?: study)?')
    completed, unknown, ongoing = [], False, False
    completed_levels, ongoing_levels = [], []
    def level(label):
        return 1 if 'scoping' in label else 2 if re.search(r'pre|\bpfs\b', label) else 3
    # Each status binds to one adjacent study mention, never to a whole clause.
    clauses = re.split(r'[;；.!?]|\bbut\b|\bwhile\b|\band\b', t)
    for clause in clauses:
        matches = list(study.finditer(clause))
        if not matches:
            continue
        for index, m in enumerate(matches):
            # A directly parenthesized acronym is the same mention, not a second study.
            if index and level(matches[index-1].group()) == level(m.group()) and re.fullmatch(r'\s*\(\s*', clause[matches[index-1].end():m.start()]) and clause[m.end():].lstrip().startswith(')'):
                continue
            previous_end = matches[index-1].end() if index else 0
            next_start = matches[index+1].start() if index+1 < len(matches) else len(clause)
            prefix, suffix = clause[previous_end:m.start()], clause[m.end():next_start]
            done = bool(
                re.search(r'(?:\bcompleted\s+(?:the\s+|a\s+|its\s+)?|\bcompletion\s+of\s+(?:the\s+|a\s+|its\s+)?|已揭露完成\s*|已完成\s*)$', prefix)
                or re.match(r'\s*(?:(?:was|is|has been|had been)\s+)?completed\b', suffix))
            progress = bool(
                re.search(r'(?:\b(?:ongoing|planned|planning|commencing|undertaking)\s+(?:a\s+|the\s+)?|currently\s+(?:the\s+)?subject\s+of\s+(?:a\s+|the\s+)?|進行中\s*|預計\s*)$', prefix)
                or re.match(r'\s*(?:(?:is|was|currently|is currently)\s+)?(?:in progress|underway|planned|ongoing|work was progressed|進行中|預計)', suffix))
            conditional = bool(re.search(future, prefix)) or bool(re.match(r'\s*(?:will|would|could|may|might)\b', suffix))
            if conditional:
                progress = True
                done = False
            if progress:
                ongoing = True
                ongoing_levels.append(level(m.group()))
                if done:
                    return finish('CONFLICTING_STUDY_COMPLETION_FOR_SAME_STUDY')
                continue
            if not done:
                unknown = True
                continue
            label = m.group()
            completed.append('B1' if re.search(r'scoping|pre|\bpfs\b', label) else 'B2')
            completed_levels.append(level(label))
    if completed_levels and ongoing_levels and max(completed_levels) >= min(ongoing_levels):
        return finish('CONTRADICTORY_COMPLETED_AND_IN_PROGRESS_STUDIES')
    if unknown:
        return finish('STUDY_COMPLETION_NOT_EXPLICIT')
    if completed:
        return finish('HIGHEST_EXPLICIT_COMPLETED_STUDY', max(completed), ongoing)
    if ongoing:
        return finish('IN_PROGRESS_WITHOUT_COMPLETED_PREVIOUS_STUDY')
    if re.search(r'explor|drill|\btarget\b|\btarget areas\b|reconnaissance|探勘|勘探', t):
        if has_mre is None:
            return finish('SELECTED_MRE_STATUS_UNVERIFIED')
        return finish('EXPLORATION_SELECTED_MRE_SPLIT', 'A2' if has_mre else 'A1')
    return finish('UNMAPPED_STAGE_REQUIRES_REVIEW')


def stage_rule_fills(row, provenance, decisions):
    native = _native(row, provenance, '開發階段')
    if native is None or not native.get('locator'):
        return []
    # A classification preserves the dated disclosure, not a current-status claim.
    # Missing completion dates are not replaced with publication dates; both roles
    # remain distinct in the retained source provenance.
    def valid_date(value):
        value = str(value or '')
        if not re.fullmatch(r'\d{4}(?:-\d{2}){1,2}', value):
            return False
        try:
            date.fromisoformat(value+'-01' if len(value)==7 else value)
            return True
        except ValueError:
            return False
    dated = any(valid_date(native.get(k)) for k in ('effective_date', 'publication_date', 'document_issue_date'))
    if not dated:
        return []
    has_mre, mre_evidence = selected_mre(row, provenance)
    proposal = classify_stage(row.get('開發階段'), has_mre)
    if proposal['code'] is None:
        return []
    decision = approved_decision(decisions, proposal['rule'])
    if decision is None:
        return []
    extra = None
    if proposal.get('ongoing_study'):
        extra = approved_decision(decisions, 'IN_PROGRESS_STUDY_USE_HIGHEST_EXPLICIT_COMPLETED')
        if extra is None:
            return []
    # Never create a code/category tuple contradictory to an existing value.
    values = {'開發階段代碼': proposal['code'], '開發階段類別': proposal['category']}
    if any(row.get(c, '') not in ('', value) for c, value in values.items()):
        return []
    return [dict(column=c, value=value, sha=native['source_sha256'],
                 locator=native.get('locator', '')+'; researcher stage rule '+decision['decision_id'],
                 method='APPROVED_RESEARCHER_STAGE_RULE',
                 scope=canonical(dict(decision_id=decision['decision_id'], rule=decision['rule'],
                     decision=decision, additional_decision=extra, source_value=row['開發階段'],
                     source_provenance=native, selected_mre=has_mre, mre_basis=mre_evidence,
                     temporal_scope='AT_NATIVE_SOURCE_DATE_NOT_CURRENT_STATUS')))
            for c, value in values.items() if row.get(c, '') == '']


def deposit_decision_sheet(rows):
    """All unmapped project rows count, including missing native descriptions."""
    counts = Counter(r.get('礦床型態', '') for r in rows if r.get('礦床型態代碼', '') == '')
    return [dict(source_text=text, project_count=count, candidate_codes='hard|iac|placer' if text else '',
                 reason='RESEARCHER_MUST_SELECT;GENERIC_CLAY_REGOLITH_NOT_ION_ADSORPTION' if text else 'NO_NATIVE_DEPOSIT_DESCRIPTION')
            for text, count in sorted(counts.items())]
