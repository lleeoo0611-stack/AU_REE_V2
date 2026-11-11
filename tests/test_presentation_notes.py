"""Presentation migration contracts, provenance replay and historical compatibility."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from au_ree_v2.iteration_review import audit_summary, review_coverage_cycle
from au_ree_v2.presentation_notes import (ARCHIVE, NEW, OLD, VERSION, _read, _write,
                                          convert_summary)
from au_ree_v2.store import filehash


class PresentationNotesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'core'
        self.source.mkdir()
        self.cols = json.loads((Path(__file__).resolve().parents[1] / 'config/project_summary_columns_legacy52.json').read_text('utf8')) + ['ASX代碼']
        rows = []
        for pid in ('splinter', 'circle', 'dated', 'point', 'no-note'):
            row = dict.fromkeys(self.cols, '')
            row['專案ID'] = pid
            rows.append(row)
        rows[0][OLD] = '來源以Ce2O3表示；依研究者決定以化學計量換算為CeO2（係數1.0487434078）；TREO依SOURCE_TREO_PLUS_Y_MINUS_CE2O3_PLUS_CEO2重算；15項氧化物總和與TREO於來源有效位數範圍內一致'
        rows[0]['CeO2_氧化鈰_kt'] = '1.0487434078'
        rows[1][OLD] = 'NdPr為來源公布之合計氧化物品位；Nd、Pr個別值未公布'
        rows[1]['NdPr蘊藏量_kt_需兩者皆公布'] = '1.2'
        rows[2]['開發階段'] = 'Exploration（來源揭露：2023-02）'
        rows[2]['開發階段代碼'] = 'A2'
        rows[3]['緯度'] = '-33'
        rows[3]['經度'] = '122'
        self.pfields = ['project_id', 'column', 'value', 'source_sha256', 'source_url', 'locator', 'method', 'scope', 'source_kind']
        prov = []
        for row in rows:
            for column, value in row.items():
                if value:
                    record = dict.fromkeys(self.pfields, '')
                    record.update(project_id=row['專案ID'], column=column, value=value,
                                  source_sha256='a' * 64, source_url='https://example.org/source', locator='p1', method='SOURCE')
                    if row['專案ID'] == 'point' and column in ('緯度', '經度'):
                        record.update(source_kind='GOVERNMENT_SPATIAL_CATALOGUE', scope=json.dumps(dict(dataset='WA_MINEDEX',distance_check='NO_VERIFIED_DISTANCE_COMPARATOR')))
                    prov.append(record)
        self.rows = rows
        _write(self.source / '專案總表.csv', self.cols, rows)
        _write(self.source / 'field_provenance.csv', self.pfields, prov)
        _write(self.source / 'missing_fields.csv', ['project_id','column','reason','blank_class','blank_rule_id'], [dict(project_id=r['專案ID'],column=c,reason='UNKNOWN') for r in rows for c,v in r.items() if not v])
        summary = dict(version='census-project-summary-v3-asx-identity', base_contract_columns=52,
                       identity_ledger_sha256='b'*64, filled_counts={c: sum(bool(r[c]) for r in rows) for c in self.cols})
        self.save_summary(self.source, summary)
        self.out = self.root / 'presentation'

    def save_summary(self, folder, summary):
        names = ['專案總表.csv','field_provenance.csv','missing_fields.csv']
        if (folder / ARCHIVE).exists():
            names.append(ARCHIVE)
        summary['output_hashes'] = {name:filehash(folder/name) for name in names}
        (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False),encoding='utf8')

    def test_exact_replacement_determinism_and_core_immutability(self):
        original = {p.name:p.read_bytes() for p in self.source.iterdir()}
        a = convert_summary(self.source,self.out)
        second = self.root/'second'
        b = convert_summary(self.source,second)
        self.assertEqual(a,b)
        for p in self.out.iterdir():
            self.assertEqual(p.read_bytes(),(second/p.name).read_bytes())
        self.assertEqual(original,{p.name:p.read_bytes() for p in self.source.iterdir()})
        columns,rows=_read(self.out/'專案總表.csv')
        self.assertEqual(columns.index(NEW),self.cols.index(OLD))
        self.assertNotIn(OLD,columns)
        self.assertEqual(len(columns),53)
        for old,new in zip(self.rows,rows):
            for c in self.cols:
                if c != OLD:self.assertEqual(old[c],new[c])
        self.assertEqual(rows[-1][NEW],'')
        self.assertIn('目前',rows[2][NEW])
        self.assertIn('2023-02',rows[2][NEW])
        self.assertIn('NO_VERIFIED_DISTANCE_COMPARATOR',rows[3][NEW])
        self.assertIn('1.0487434078',rows[0][NEW])
        self.assertNotIn('留白',rows[0][NEW])
        self.assertIn('個別值未公布',rows[1][NEW])

    def test_trace_archive_and_evidence_coverage(self):
        core=audit_summary(self.source)
        result=convert_summary(self.source,self.out)
        _,prov=_read(self.out/'field_provenance.csv')
        self.assertFalse(any(p['column']==OLD for p in prov))
        archive=json.loads((self.out/ARCHIVE).read_text('utf8'))
        self.assertEqual(len(archive['provenance']),2)
        notes=[p for p in prov if p['column']==NEW]
        self.assertEqual(len(notes),4)
        for note in notes:
            sources=json.loads(note['scope'])['source_records']
            self.assertTrue(sources)
            self.assertTrue(all(s['source_sha256'] and s['method'] and s['locator'] for s in sources))
        metrics=result['coverage_metrics']
        self.assertEqual(metrics['original_53_column_evidence']['filled_cells'],core['filled_cells'])
        self.assertEqual(metrics['remaining_52_columns']['filled_cells'],core['filled_cells']-2)
        self.assertEqual(metrics['final_53_column_presentation']['filled_cells'],core['filled_cells']+2)
        self.assertFalse(metrics['note_cells_are_scientific_evidence_gain'])
        self.assertEqual(result['scientific_filled_cells'],core['scientific_filled_cells'])

    def test_reject_tampered_mapping_and_counts(self):
        convert_summary(self.source,self.out)
        summary=json.loads((self.out/'summary.json').read_text('utf8'))
        summary['presentation_mapping']['replaced_index']=0
        self.save_summary(self.out,summary)
        with self.assertRaisesRegex(ValueError,'MAPPING'):audit_summary(self.out)
        summary['presentation_mapping']['replaced_index']=self.cols.index(OLD)
        summary['coverage_metrics']['original_53_column_evidence']['filled_cells']+=1
        self.save_summary(self.out,summary)
        with self.assertRaisesRegex(ValueError,'COVERAGE'):audit_summary(self.out)

    def test_reject_note_fabrication_even_with_matching_provenance_and_hashes(self):
        convert_summary(self.source,self.out)
        columns,rows=_read(self.out/'專案總表.csv')
        rows[0][NEW]='All oxide values remain blank'
        _write(self.out/'專案總表.csv',columns,rows)
        fields,prov=_read(self.out/'field_provenance.csv')
        next(p for p in prov if p['project_id']=='splinter' and p['column']==NEW)['value']=rows[0][NEW]
        _write(self.out/'field_provenance.csv',fields,prov)
        self.save_summary(self.out,json.loads((self.out/'summary.json').read_text('utf8')))
        with self.assertRaisesRegex(ValueError,'NOTE_MISMATCH'):audit_summary(self.out)

    def test_old_53_audit_and_no_presentation_coverage_cycle(self):
        self.assertEqual(audit_summary(self.source)['columns'],53)
        convert_summary(self.source,self.out)
        with self.assertRaisesRegex(ValueError,'CANONICAL_EVIDENCE'):review_coverage_cycle(self.out,self.out,{})

    def test_no_in_place_or_repeated_conversion(self):
        with self.assertRaisesRegex(ValueError,'SEPARATE'):convert_summary(self.source,self.source)
        convert_summary(self.source,self.out)
        with self.assertRaisesRegex(ValueError,'CANONICAL'):convert_summary(self.out,self.root/'third')

    def test_core_changes_rejected_even_when_output_hashes_refreshed(self):
        convert_summary(self.source,self.out)
        columns,rows=_read(self.out/'專案總表.csv')
        rows[0]['CeO2_氧化鈰_kt']='99'
        _write(self.out/'專案總表.csv',columns,rows)
        fields,prov=_read(self.out/'field_provenance.csv')
        next(p for p in prov if p['project_id']=='splinter' and p['column']=='CeO2_氧化鈰_kt')['value']='99'
        _write(self.out/'field_provenance.csv',fields,prov)
        self.save_summary(self.out,json.loads((self.out/'summary.json').read_text('utf8')))
        with self.assertRaisesRegex(ValueError,'CORE_CONTENT'):audit_summary(self.out)

    def test_core_source_metadata_changes_rejected(self):
        convert_summary(self.source,self.out)
        fields,prov=_read(self.out/'field_provenance.csv')
        next(p for p in prov if p['project_id']=='splinter' and p['column']=='CeO2_氧化鈰_kt')['method']='FABRICATED'
        _write(self.out/'field_provenance.csv',fields,prov)
        self.save_summary(self.out,json.loads((self.out/'summary.json').read_text('utf8')))
        with self.assertRaisesRegex(ValueError,'CORE_PROVENANCE'):audit_summary(self.out)

    def test_original_missing_reason_hash_is_enforced(self):
        convert_summary(self.source,self.out)
        fields,missing=_read(self.out/'missing_fields.csv')
        next(p for p in missing if p['column']!=NEW)['reason']='FABRICATED'
        _write(self.out/'missing_fields.csv',fields,missing)
        summary=json.loads((self.out/'summary.json').read_text('utf8'))
        summary.pop('blank_coverage',None)
        self.save_summary(self.out,summary)
        with self.assertRaisesRegex(ValueError,'CORE_GAP_HASH'):audit_summary(self.out)

    def test_unsupported_source_csv_serialization_is_rejected(self):
        path=self.source/'專案總表.csv'
        path.write_bytes(path.read_bytes().replace(b'\r\n',b'\n'))
        self.save_summary(self.source,json.loads((self.source/'summary.json').read_text('utf8')))
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_CORE_SERIALIZATION'):convert_summary(self.source,self.out)

    def test_existing_destination_is_preserved(self):
        self.out.mkdir()
        marker=self.out/'unrelated.txt'
        marker.write_text('keep',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'FRESH_OUTPUT'):convert_summary(self.source,self.out)
        self.assertEqual(marker.read_text('utf8'),'keep')
        self.assertEqual(list(self.out.iterdir()),[marker])
