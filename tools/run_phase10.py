"""Run/reproduce the Phase 10 audits without altering the formal database."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from au_ree_v2 import phase10_quality, phase10_recovery
from au_ree_v2.derived_cache import atomic_json
from au_ree_v2.store import filehash

from tools import phase10_baseline, phase10_gaps, phase10_repository, phase10_shadow


RESULTS = Path('results/phase10-2026-11-27')
CALIBRATION_FRAME = Path('config/ontology/resource_admission_round9_frame_v1.json')


def _read(path):
    return json.loads(path.read_bytes()) if path.is_file() else {}


def quality(root, output, work, manifest, *, assets=None, fetch=False, regression=None):
    if fetch:
        assets = phase10_shadow.stage_frozen_pdfs(root, manifest, work / 'holdout-originals')
    holdout_receipt = output / 'holdout_shadow_receipt.json'
    phase10_shadow.run(root, manifest, holdout_receipt, assets=assets)
    holdout = phase10_quality.run(root, output / 'quality_holdout', manifest, admission=holdout_receipt, assets=assets)
    if regression:
        phase10_quality.run(root, output / 'quality_regression', root / CALIBRATION_FRAME,
                            admission=regression, assets=assets)
    return holdout


def _rate(metric):
    if metric.get('status') != 'MEASURED':
        return '未量測'
    return f'{metric["numerator"]}／{metric["denominator"]}'


def report(output):
    """Render a compact ledger while preserving every denominator in its own receipt."""
    output = Path(output)
    baseline = _read(output / 'phase10_baseline.json')
    census = baseline.get('census', {})
    recovery = _read(output / 'source_recovery_manifest.json')
    holdout = _read(output / 'quality_holdout/quality_measurement.json')
    calibration = _read(output / 'quality_regression/quality_measurement.json')
    gaps = _read(output / 'project_criterion_blockers.json')
    shadow = _read(output / 'holdout_shadow_receipt.json').get('counts', {})
    archive = baseline.get('archive_mcda', {})
    effects = _read(output / 'factor-effects.json').get('effects', {})
    archived_effects = _read(output / 'reference-effects.json').get('historical_phase22', {})
    performance = _read(output / 'performance.json')
    archive_performance = _read(output / 'reference-performance.json')
    subset = _read(output / 'verified-subset.json')
    repo = _read(output / 'repository_integration.json')
    coverage = census.get('current_coverage')
    coverage_text = f'{coverage * 100:.2f}%' if isinstance(coverage, (int, float)) else '詳見逐格收據'
    fixed = census.get('historical_fixed_coverage')
    fixed_text = f'。保留原發布固定分母時為 {fixed * 100:.2f}%' if isinstance(fixed, (int, float)) else ''
    rows = [
        '# Phase 10 自動證據品質、來源恢復與研究增益', '',
        '## 封存基準與重播界線', '',
        f'研究截日為 **{baseline.get("cutoff", "2026-11-13")}**。封存 Census 有 **{census.get("projects", "未量測")} 案、'
        f'{census.get("columns", "未量測")} 欄**，適用覆蓋率 {coverage_text}，缺值 {census.get("missing_applicable", "未量測")} 格{fixed_text}。'
        f'已核對 {archive.get("panel_count", "未量測")} 份封存面板排名。 [基準](phase10_baseline.md)', '',
        '## 原件恢復', '',
        f'{recovery.get("verified_assets", "未量測")}／{recovery.get("locked_assets", "未量測")} 份原件已核對。'
        f'相對前次同鎖檔增 {recovery.get("net_new_exact_vs_prior", "未量測")} 份，尚缺 {recovery.get("source_unavailable", "未量測")} 份。'
        f'完整 93 案歷史重建狀態為 `{recovery.get("historical_93", {}).get("status", "UNMEASURED")}`。'
        '不同 SHA 的回應及逐件阻礙另有紀錄。 [來源恢復](source_recovery_report.md)', '',
        '## 留出、Silver 參照與品質', '',
        f'留出驗證 {shadow.get("verified_sources", "未量測")}／{shadow.get("source_count", "未量測")} 份原件，'
        f'{shadow.get("candidate_rows", "未量測")} 列資源與 {shadow.get("technical_candidate_rows", "未量測")} 列技術候選。'
        '留出原件於研究截日之後收錄，保留在影子評估。數值真值不足的指標列為未量測。 [留出](holdout_manifest.json) · [留出量測](quality_holdout/quality_measurement.json)', '',
        f'另在封存校準範圍取得 {calibration.get("classes", {}).get("DETERMINISTIC_VERIFIED", "未量測")} 筆可驗證參照。'
        f'數值與單位的一致率分別為 {_rate(calibration.get("silver_numeric_extraction_agreement", {}))}、'
        f'{_rate(calibration.get("silver_unit_extraction_agreement", {}))}。這兩個分母都是可配對參照。'
        '解析器一致、合成案例及未量測的獨立準確率分開列出。 [校準量測](quality_regression/quality_measurement.json)', '',
        '## 缺值、正式選值與研究增益', '',
        f'已計算 {gaps.get("priority_row_count", "未量測")} 個專案與準則的優先序，'
        f'自動填入的正式值為 {gaps.get("automatic_new_values", "未量測")}。面板可能增加的條件式樣本另列。'
        '缺件恢復先改善可重播性，完整歷史面板的可用資料增減仍取決於同口徑重播。 [優先序](research_gap_priority.csv) · [阻礙](project_criterion_blockers.json)', '',
        '## 因素與工程驗證', '',
    ]
    rows.extend(f'- `{name}` 為 `{item.get("status", "UNMEASURED")}`。' for name, item in sorted(effects.items()))
    if archived_effects:
        old = archived_effects['effects']
        c1 = old['c1_cohort_policy']
        admission = old['resource_admission_enablement']
        rows.append(f'- 封存 Phase 22 的 C1 政策對照涵蓋 {c1["panel_count_in_comparator"]} 個面板，'
                    f'名次變動 {c1["panel_totals"]["rank_position_cells_changed"]} 格。'
                    f'採納啟用單獨改動 {admission["selection_counts"]["updated"]} 個選值、'
                    f'{admission["panel_totals"]["matrix_primary_criterion_cells_changed"]} 個矩陣格及 '
                    f'{admission["panel_totals"]["ranking_score_cells_changed"]} 個分數，名次變動 '
                    f'{admission["panel_totals"]["rank_position_cells_changed"]} 格。'
                    '檢索、換算和聯合規則遷移另列。 [封存因素對照](reference-effects.json)')
    elif not effects:
        rows.append('- 尚未取得同範圍因素對照收據。')
    if effects:
        rows.append('- 本輪固定歷史輸入的逐項實驗附有差異收據。 [因素](factor-effects.json)')
    if subset:
        rows.append('- 另有 11 月 5 日鎖檔的可用子集重播收據。 [子集](verified-subset.json)')
    if performance:
        equivalence = performance['equivalence']
        times = '／'.join(f'{performance["runs"][f"current-full-{mode}"]["proc_wall_seconds"]:.2f}' for mode in ('off', 'cold', 'warm'))
        rows.append(f'- 停用、冷、暖快取各耗時 {times} 秒。'
                    f'{equivalence["baseline_scientific_artifacts"]} 項科學產物的快取等價性為 '
                    f'`{equivalence["status"]}`。 [效能](performance.json)')
    if archive_performance:
        rows.append(f'- 封存快取驗證為 `{archive_performance["reference_scientific_status"]}`，已比對 '
                    f'{archive_performance["reference_scientific_artifacts_checked"]} 項科學產物。 [封存效能](reference-performance.json)')
    rows.extend(['',
        f'已盤點 {len(repo.get("remote_tips", []))} 個遠端分支。封存圖和新工具的相依、複雜度及重複群組另有收據。'
        'CI 依變更區分單元、PDF 至 R 整合與完整歷史重播，發布路徑保留公開來源驗證。'
        ' [分支](repository_integration.json) · [模組](phase10_module_audit.json) · [CI 效能](ci-performance.json)', '',
        '尚未分離的正式效果及缺少獨立真值的指標維持未量測。', '',
    ])
    (output / 'PHASE10_REPORT.md').write_text('\n'.join(rows), encoding='utf-8')
    atomic_json(output / 'phase10_report_inputs.json', {name: filehash(output / name) for name in (
        'phase10_baseline.json', 'source_recovery_manifest.json', 'holdout_manifest.json', 'holdout_shadow_receipt.json',
        'quality_holdout/quality_measurement.json', 'quality_regression/quality_measurement.json', 'reference-effects.json',
        'project_criterion_blockers.json', 'factor-effects.json', 'performance.json', 'repository_integration.json',
        'phase10_module_audit.json', 'ci-performance.json', 'reference-performance.json',
        'verified-subset.json') if (output / name).is_file()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('run', 'quality', 'report'), default='run')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--out', type=Path)
    parser.add_argument('--work', type=Path, default=Path('work/phase10'))
    parser.add_argument('--assets', type=Path)
    parser.add_argument('--library', type=Path, action='append', default=[])
    parser.add_argument('--online', action='store_true')
    parser.add_argument('--fetch-holdout', action='store_true')
    parser.add_argument('--regression-receipt', type=Path)
    parser.add_argument('--replay-factors', action='store_true')
    parser.add_argument('--previous-recovery', type=Path)
    parser.add_argument('--pulls', type=Path)
    parser.add_argument('--ci', type=Path, action='append', default=[])
    args = parser.parse_args()
    root, work = args.root.resolve(), args.work.resolve()
    output = (args.out or root / RESULTS).resolve()
    manifest = root / RESULTS / 'holdout_manifest.json'
    if output == root or any(output.is_relative_to(root / part) for part in ('data', 'config')):
        raise ValueError('Phase 10 outputs must use a separate report directory')
    output.mkdir(parents=True, exist_ok=True)
    if args.mode == 'report':
        phase10_repository.record(root, output / 'repository_integration.json', pulls=args.pulls, ci=args.ci)
        report(output)
        return
    assets = args.assets
    if args.mode == 'run':
        libraries = (*args.library, *((assets,) if assets else ()))
        phase10_recovery.run(root, output, work=work / 'recovery', libraries=libraries,
                             online=args.online, previous=args.previous_recovery)
        phase10_baseline.run(root, output, recovery_manifest=work / 'recovery/recovery.json')
        phase10_gaps.run(root, output, output / 'source_recovery_manifest.json')
        assets = work / 'recovery/assets'
    if output / 'holdout_manifest.json' != manifest:
        (output / 'holdout_manifest.json').write_bytes(manifest.read_bytes())
    quality(root, output, work, manifest, assets=assets, fetch=args.fetch_holdout, regression=args.regression_receipt)
    if args.mode == 'run':
        if args.replay_factors:
            subprocess.run([sys.executable, '-m', 'tools.run_phase10_factor_replays', '--root', str(root),
                            '--work', str(work / 'factor-runs'), '--out', str(output)], cwd=root, check=True)
        phase10_repository.record(root, output / 'repository_integration.json', pulls=args.pulls, ci=args.ci)
        report(output)


if __name__ == '__main__':
    main()
