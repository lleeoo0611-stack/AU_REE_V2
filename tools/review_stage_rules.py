"""Offline task-3 diagnostics; approved promotion belongs to the canonical exporter."""
import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
from au_ree_v2.stage_rules import (classify_stage, selected_mre, stage_rule_fills,
    proposed_decisions, deposit_decision_sheet, decision_records)
from au_ree_v2.store import filehash


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, columns):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def run(baseline, out, decisions=None, projected=None):
    baseline, out = Path(baseline).resolve(), Path(out).resolve()
    if out.exists() or out == baseline or baseline in out.parents:
        raise ValueError('STAGE_REQUIRES_FRESH_ISOLATED_OUTPUT')
    decisions = decision_records(decisions) if decisions else proposed_decisions()
    rows = read_csv(baseline / '專案總表.csv')
    trace = read_csv(baseline / 'field_provenance.csv')
    proposals, queue, fills = [], [], []
    for row in rows:
        if row.get('開發階段代碼') and row.get('開發階段類別'):
            continue
        mre, basis = selected_mre(row, trace)
        proposal = classify_stage(row.get('開發階段'), mre)
        proposal.update(project_id=row['專案ID'], selected_mre=mre, mre_basis=json.dumps(basis, ensure_ascii=False, sort_keys=True))
        proposals.append(proposal)
        fills.extend(dict(project_id=row['專案ID'], **fill) for fill in stage_rule_fills(row, trace, decisions))
        if proposal['code'] is None and row.get('開發階段', ''):
            queue.append(dict(project_id=row['專案ID'], source_text=row.get('開發階段', ''), reason=proposal['reason']))
    if fills and projected is None:
        raise ValueError('APPROVED_STAGE_RULES_REQUIRE_CANONICAL_REBUILD_PROJECTED_OUTPUT')
    source = Path(projected).resolve() if projected else baseline
    new_rows = read_csv(source / '專案總表.csv')
    old = {r['專案ID']: r for r in rows}
    allowed = {(f['project_id'], f['column']): str(f['value']) for f in fills}
    if [r['專案ID'] for r in new_rows] != [r['專案ID'] for r in rows]:
        raise ValueError('STAGE_PROJECTION_PROJECT_ORDER_CHANGED')
    new_cells = []
    for row in new_rows:
        for col, value in row.items():
            before = old[row['專案ID']][col]
            if value != before:
                if before != '' or allowed.get((row['專案ID'], col)) != value:
                    raise ValueError('STAGE_PROJECTION_UNAUTHORIZED_CELL_CHANGE')
                new_cells.append(dict(project_id=row['專案ID'], column=col, old_value=before, new_value=value))
    names = ['專案總表.csv', 'field_provenance.csv', 'missing_fields.csv', 'census_inventory.csv', 'summary.json', 'audit.json']
    for name in names:
        if not (source / name).is_file():
            raise ValueError('STAGE_BASELINE_FILE_MISSING:'+name)
        if not fills and (source / name).read_bytes() != (baseline / name).read_bytes():
            raise ValueError('UNAPPROVED_STAGE_OUTPUT_BYTES_CHANGED:'+name)
    out.mkdir(parents=True)
    # Preserve canonical output under projection/, keeping task summary.json distinct.
    projection = out / 'projection'
    projection.mkdir()
    for name in names:
        shutil.copyfile(source / name, projection / name)
    write_csv(out / 'new_cells.csv', new_cells, ['project_id', 'column', 'old_value', 'new_value'])
    write_csv(out / 'changed_cells.csv', [], ['project_id', 'column', 'old_value', 'new_value'])
    write_csv(out / 'review_queue.csv', queue, ['project_id', 'source_text', 'reason'])
    write_csv(out / 'stage_rule_proposals.csv', proposals, ['source_text', 'code', 'category', 'rule', 'reason', 'ongoing_study', 'project_id', 'selected_mre', 'mre_basis'])
    sheet = deposit_decision_sheet(rows)
    write_csv(out / 'deposit_type_decision_sheet.csv', sheet, ['source_text', 'project_count', 'candidate_codes', 'reason'])
    (out / 'proposed_decisions.json').write_text(json.dumps({'decisions': proposed_decisions()}, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    summary = dict(task='task3-stage-rules', network_requests=0, new_cells=len(new_cells), changed_cells=0,
                   candidate_projects=sum(p['code'] is not None for p in proposals), review_queue=len(queue),
                   hypothetical_approved_preview_cells=sum(2 for p in proposals if p['code'] is not None),
                   hypothetical_preview_is_not_production=True,
                   no_native_stage_projects=sum(not p['source_text'] for p in proposals),
                   deposit_unmapped_project_rows=sum(r['project_count'] for r in sheet),
                   deposit_distinct_descriptions=len(sheet),
                   baseline_filled=sum(v != '' for r in rows for v in r.values()),
                   output_filled=sum(v != '' for r in new_rows for v in r.values()),
                   approvals_default_null=True, canonical_output_hashes={n:filehash(projection/n) for n in names},
                   disabled_outputs_byte_identical=all((baseline/n).read_bytes()==(projection/n).read_bytes() for n in names))
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    (out / 'README.md').write_text('# 任務 3：開發階段核准閘門\n\n'
        '本次只使用既有總表及 provenance，網路請求為零。提案 decided_by 全部預設 null；不得由程式代填。\n\n'
        f'新增 {len(new_cells)} 格，既有值變更 0 格；候選專案 {summary["candidate_projects"]} 案，待審 {len(queue)} 案。\n\n'
        '研究僅有名稱不等於已完成；無明示完成的 Scoping、PFS、DFS、BFS 或 Feasibility 留待審，因此可能低於預期格數。'
        '進行中研究只採同原文明示已完成的上一階；Operating 不推成 D3；退出不推成 X；A3 不自動指派。\n\n'
        f'礦床型態決定表含 {summary["deposit_unmapped_project_rows"]} 個未對照專案（含原文缺失），按原文彙總；候選代碼只列可選詞彙，不是分類結論。\n\n'
        'projection/ 保存四份 canonical CSV 及 summary／audit。未核准時逐位元保留基線；task summary.json 是診斷摘要，與 canonical summary 分開。'
        '核准後必須由既有 canonical exporter 重建，再用 --projected 指定結果，不能由此工具直接改表。\n', encoding='utf8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--decisions', type=Path)
    parser.add_argument('--projected', type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.baseline, args.out, args.decisions, args.projected), ensure_ascii=False, indent=2))
