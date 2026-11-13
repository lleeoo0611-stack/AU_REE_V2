"""Round-five publication: verify four accepted tasks before rollback-capable swap."""
import json,shutil
from pathlib import Path
from .round2_pipeline import FILES,read_csv,write_json
from .round3_publication import tree_hashes,publish_transaction
from .round3_release import verify_public_tree
from .store import filehash

def publish(repo,date,work,out,expected,tests_pass):
    from . import round4_schema as schema
    repo,work,out=map(Path,(repo,work,out));current=repo/'results/asx-current'
    if tree_hashes(current)!=expected:raise ValueError('ROUND5_CURRENT_CHANGED')
    records=[];census=set()
    for n in range(1,5):
        folder=repo/f'results/round5-{n}-{date}'
        r=json.loads((folder/'rebuild_receipt.json').read_text('utf8'));s=json.loads((folder/'summary.json').read_text('utf8'))
        if r.get('independent_full_rebuilds')!=2 or s.get('independent_full_rebuilds')!=2:raise ValueError('ROUND5_DOUBLE_REBUILD_REQUIRED')
        if set(r['output_hashes'])!=set(FILES) or any(filehash(folder/'projection'/f)!=h for f,h in r['output_hashes'].items()):raise ValueError('ROUND5_ACCEPTED_OUTPUT_CHANGED')
        if s['bitwise_identical_files']!=r['output_hashes'] or tests_pass(folder/'offline-tests.xml')!=r['tests'] or r['tests']!=s['tests']:raise ValueError('ROUND5_TEST_RECEIPT_CHANGED')
        if s.get('bitwise_identical_audit_files')!=r.get('audit_hashes') or not r.get('audit_hashes'):raise ValueError('ROUND5_AUDIT_RECEIPT_REQUIRED')
        if any(filehash(folder/f)!=h for f,h in r['audit_hashes'].items()):raise ValueError('ROUND5_AUDIT_CHANGED')
        schema.audit(folder/'projection',repo);verify_public_tree(folder)
        from tools.run_round5 import verify_existing
        verify_existing(folder/'projection')
        census.add(r['census_sha256']);records.append(s)
    if len(census)!=1:raise ValueError('ROUND5_CENSUS_CHANGED')
    a=work/'presentation-a';b=work/'presentation-b'
    schema.present(out/'projection',a,repo);schema.present(out/'projection',b,repo)
    if tree_hashes(a)!=tree_hashes(b):raise ValueError('ROUND5_PRESENTATION_NOT_IDENTICAL')
    staged=current.with_name('asx-current.round5-staged-'+date);backup=current.with_name('asx-current.pre-round5-'+date)
    if staged.exists() or backup.exists():raise ValueError('ROUND5_FRESH_PUBLICATION_REQUIRED')
    shutil.copytree(a,staged)
    for f in ('source_consistency.csv','retired_consistency_trace.json','numeric_presentation_original.json','numeric_presentation_changes.json'):
        if (current/f).is_file():shutil.copyfile(current/f,staged/f)
    status=json.loads((current/'publication_status.json').read_text('utf8'))
    previous=json.loads(json.dumps(status));status.setdefault('history',[]).append(dict(status='ROUND5_RESEARCHER_APPROVED_PUBLISHED',previous_publication_status=previous,published=True,accepted_tasks=list(range(1,5)),date=date,new_research_cells=sum(r['new_cells'] for r in records),merge_not_new_evidence=True,existing_conclusion='INCOMPLETE/CONTINUE_UNCHANGED'))
    status.update(published=True,status='ROUND5_RESEARCHER_APPROVED_PUBLISHED',new_cells=sum(r['new_cells'] for r in records),accepted_tasks=list(range(1,5)),backup=backup.relative_to(repo).as_posix(),swap_semantics='TWO_SAME_FILESYSTEM_RENAMES_WITH_ROLLBACK_NOT_ATOMIC_EXCHANGE')
    write_json(staged/'publication_status.json',status)
    cov=json.loads((out/'projection/summary.json').read_text('utf8'))
    display_columns,rows=read_csv(staged/'專案總表.csv');_,trace=read_csv(staged/'field_provenance.csv')
    displayed_filled=sum(bool(r[c]) for r in rows for c in display_columns);displayed_total=len(rows)*len(display_columns)
    display_coverage=dict(filled=displayed_filled,denominator=displayed_total,coverage=displayed_filled/displayed_total,projects=len(rows),columns=len(display_columns),difference_from_evidence=displayed_filled-cov['original_53_columns']['filled'],basis='DISPLAYED_TABLE_WITH_PRESERVED_NOTES_NOT_NEW_EVIDENCE')
    centers={p['project_id'] for p in trace if 'TENEMENT_CENTROID' in str(p)}
    lines=['# 第五輪研究者核准總表','',f'92 列、51 欄。新研究證據共 {sum(r["new_cells"] for r in records)} 格；同一公司更名合併及不適用分類不算新增證據。','既有總說明完整保留，WIM100 十進位呈現精度不改。INCOMPLETE／CONTINUE 結論不變。','']
    for label,key in [('原 53 欄歷史口徑','original_53_columns'),('51 欄適用口徑','all_retained_columns')]:
        m=cov[key];lines.append(f'{label}：{m["filled"]}／{m["denominator"]}（{m["coverage"]:.2%}）。')
    m=cov['tiered_coverage']['combined'];lines.append(f'兩層適用口徑：{m["filled"]}／{m["denominator"]}（{m["coverage"]:.2%}）。')
    lines.append(f'展示 CSV 另計：{displayed_filled}／{displayed_total}。總說明保留既有內容，與證據表的一致性欄不同，不把這個呈現差額當作新增研究證據。')
    lines+=['','## 礦權中心點','礦權中心點是範圍代表點，不是礦體位置；詳細方法、精度、datum、原件與持有人見 field_provenance.csv。']
    lines += [f'- {r["專案ID"]}：'+str(next((p.get('location_method') or p.get('method') for p in trace if p['project_id']==r['專案ID'] and 'TENEMENT_CENTROID' in str(p)),'')) for r in rows if r['專案ID'] in centers]
    if not centers:lines.append('本輪無通過全部條件的礦權中心點；限制詳見任務 3 待審清單。')
    mismatch={p['project_id']:p.get('holders','') for p in trace if p['project_id'] in centers and str(p.get('holder_mismatch','')).lower()=='true'}
    if mismatch:
        lines+=['','## 礦權持有人與列示開發商不同']+[f'- {pid}：官方圖層持有人 {holders}；依核准不因此排除，但不代表公司擁有該礦權。' for pid,holders in sorted(mismatch.items())]
    lines+=['','原 Mt Stirling／Yttria 重複列已依明示更名證據合併，不再作為兩筆資源加總。完整合併與衝突記錄見 ../round4-0-'+date+'/merged_rows.json。','任務 1～4 各自雙重完整離線來源重播及完整回歸通過；分母變化與新增格分開列在 ../round5-summary-'+date+'/coverage_comparison.json。']
    (staged/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    write_json(staged/'validation.json',dict(version='round5-publication-validation-v1',tasks=records,census_sha256=next(iter(census)),publication_audit=schema.audit(staged,repo),presentation_table_coverage=display_coverage,coverage_basis='CANONICAL_EVIDENCE_VIEW_WITH_ELEMENT_CONSISTENCY_COLUMN',existing_conclusion='INCOMPLETE/CONTINUE_UNCHANGED'))
    def validate(folder):return dict(audit=schema.audit(folder,repo),security=verify_public_tree(folder))
    receipt=publish_transaction(current,staged,backup,expected,validate)
    summary=repo/f'results/round5-summary-{date}';summary.mkdir(exist_ok=True)
    write_json(summary/'publication_receipt.json',receipt);write_json(summary/'publication_status.json',status)
    (summary/'README.md').write_text('# 第五輪彙總與已驗證發布\n\n任務 1～4 已依序通過雙重完整離線來源重建與完整回歸。各任務研究新增格：'+ '、'.join(str(r['task'])+'：'+str(r['new_cells']) for r in records)+'。\n\n合併去重減量、原 53 欄／51 欄／兩層適用分母及 NOT_APPLICABLE_STAGE 變化分開列於 coverage_comparison.json。展示總說明不混入證據新增量。\n\n已發布至 ../asx-current/；總說明及既有數字精度保留。各任務的待審與來源限制仍有效，不把缺資料解讀為不存在資源。INCOMPLETE／CONTINUE 不變。\n',encoding='utf8')
    return receipt
