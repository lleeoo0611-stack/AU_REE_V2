import copy
import json
import tempfile
import unittest
from pathlib import Path

import pymupdf

from au_ree_v2.reviewed_discovery import validate_issue_date, validate_discovery, calendar_date_text
from au_ree_v2.store import filehash


class DiscoveryIssueDate(unittest.TestCase):
    def test_calendar_punctuation_changes_no_date_values(self):
        self.assertEqual('28 april 2023',calendar_date_text('28th april, 2023'))
        self.assertEqual('31 january 2023',calendar_date_text('31 january, 2023'))
        self.assertEqual('28 april 2024',calendar_date_text('28 april, 2024'))
        self.assertEqual('28, april 2023',calendar_date_text('28, april 2023'))
    def test_ordinal_publication_header_preserves_exact_calendar_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); doc=pymupdf.open(); page=doc.new_page()
            page.insert_text((40,40),'30th October 2025\nKnown Project in Queensland')
            doc.save(root/'original.pdf');doc.close();sha=filehash(root/'original.pdf')
            source=dict(asset_set='test',path='original.pdf',sha256=sha,url='https://issuer.example/original.pdf',
                kind='pdf',evidence=[dict(page=1,markers=['Known Project'])])
            identity=dict(source_index=0,source_key='test',publication_date='2025-10-30',
                date_evidence=dict(page=1,markers=['30th October 2025']),project_evidence=dict(page=1,markers=['Known Project']),
                name_marker='Known Project',state='QLD',state_marker='Queensland')
            candidate=dict(candidate_key='known',name='Known Project',aliases=[],decision='ADMIT_PROJECT',
                reason='Test',country='AU',scope='Test',sources=[source],identity=identity)
            cfg=dict(version='reviewed-project-discovery-v1',cutoff='2026-11-05',acquired_through='2026-11-10',candidates=[candidate])
            ledger=root/'ledger.json'
            (root/'downloads.json').write_text(json.dumps([dict(url=source['url'],document_sha256=sha,status='PDF_ACQUIRED')]))
            for day,valid in [('2025-10-30',True),('2025-10-31',False),('2024-10-30',False)]:
                identity['publication_date']=day;ledger.write_text(json.dumps(cfg))
                if valid:self.assertEqual(1,len(validate_discovery(ledger,{'test':root},[],'2026-11-05')['projects']))
                else:
                    with self.assertRaisesRegex(ValueError,'PUBLICATION_DATE_PROOF'):
                        validate_discovery(ledger,{'test':root},[],'2026-11-05')

    def test_official_archived_report_month_preserves_interval_and_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);doc=pymupdf.open();page=doc.new_page()
            page.insert_text((40,40),'Known Project in Northern Territory\nDate of Report: November 2024')
            doc.save(root/'original.pdf');doc.close();sha=filehash(root/'original.pdf')
            source=dict(asset_set='test',path='original.pdf',sha256=sha,url='https://archive.example.gov.au/original.pdf',kind='pdf',evidence=[dict(page=1,markers=['Known Project'])])
            identity=dict(source_index=0,source_key='test',publication_date='2024-11-30',publication_date_precision='MONTH',publication_date_interval=['2024-11-01','2024-11-30'],publication_month_role='REPORT_MONTH',publication_date_role='REPORT_MONTH_UPPER_BOUND_NOT_RELEASE_DATE',source_kind='GOVERNMENT_ARCHIVED_TECHNICAL_REPORT',date_evidence=dict(page=1,markers=['Date of Report: November 2024']),project_evidence=dict(page=1,markers=['Known Project']),name_marker='Known Project',state='NT',state_marker='Northern Territory')
            c=dict(candidate_key='known',name='Known Project',aliases=[],decision='ADMIT_PROJECT',reason='Test',country='AU',scope='Historical monthly report; release day unknown',sources=[source],identity=identity)
            cfg=dict(version='reviewed-project-discovery-v1',cutoff='2026-11-05',acquired_through='2026-11-10',candidates=[c]);ledger=root/'ledger.json'
            (root/'downloads.json').write_text(json.dumps([dict(url=source['url'],document_sha256=sha,status='PDF_ACQUIRED')]))
            ledger.write_text(json.dumps(cfg));result=validate_discovery(ledger,{'test':root},[],'2026-11-05')
            self.assertEqual(['2024-11-01','2024-11-30'],result['sources'][sha]['publication_date_interval'])
            for change in [dict(publication_date='2024-11-15'),dict(publication_date='2024-10-31',publication_date_interval=['2024-10-01','2024-10-31']),dict(publication_date_role='EXACT_RELEASE_DAY'),dict(publication_month_role='EDITION_MONTH'),dict(source_kind='ISSUER_PROJECT_IDENTITY')]:
                with self.subTest(change=change),self.assertRaises(ValueError):
                    bad=copy.deepcopy(cfg);bad['candidates'][0]['identity'].update(change);ledger.write_text(json.dumps(bad));validate_discovery(ledger,{'test':root},[],'2026-11-05')
            bad=copy.deepcopy(cfg);bad['candidates'][0]['sources'][0]['url']='https://issuer.example/original.pdf';ledger.write_text(json.dumps(bad))
            (root/'downloads.json').write_text(json.dumps([dict(url='https://issuer.example/original.pdf',document_sha256=sha,status='PDF_ACQUIRED')]))
            with self.assertRaises(ValueError):validate_discovery(ledger,{'test':root},[],'2026-11-05')

    def setUp(self):
        self.identity = {
            "publication_date": "2023-09-06",
            "document_issue_date": "2023-09-05",
            "date_evidence_role": "DOCUMENT_ISSUE_DATE_WITH_ASX_URL_RELEASE_DATE",
            "publication_date_role": "ASX_DATED_URL",
            "date_evidence": {"page": 1, "markers": ["Signed 5 September 2023"]},
        }
        self.source = {"url": "https://announcements.asx.com.au/asxpdf/20230906/pdf/abc123.pdf", "kind": "pdf"}
        self.text = "signed 5 september 2023"
        self.cutoff = "2026-11-05"

    def check(self, identity=None, source=None, text=None):
        validate_issue_date(identity or self.identity, source or self.source, self.cutoff,
                            self.text if text is None else text)

    def test_valid_roles(self):
        self.check()

    def test_ordinal_signed_date_preserves_day_month_year_and_native_markers(self):
        identity=copy.deepcopy(self.identity)
        identity['date_evidence']['markers']=['Signed 5th September 2023']
        self.check(identity=identity,text='signed 5th september 2023')
        for day in ['2023-09-04','2023-08-05','2022-09-05']:
            with self.subTest(day=day),self.assertRaises(ValueError):
                self.check(identity=dict(identity,document_issue_date=day),text='signed 5th september 2023')
        with self.assertRaises(ValueError):
            self.check(identity=identity,text='5th september 2023')

    def test_reject_url_variants(self):
        urls = [
            "https://example.org/asxpdf/20230906/pdf/abc123.pdf",
            "http://announcements.asx.com.au/asxpdf/20230906/pdf/abc123.pdf",
            "https://announcements.asx.com.au.evil.test/asxpdf/20230906/pdf/abc123.pdf",
            "https://user@announcements.asx.com.au/asxpdf/20230906/pdf/abc123.pdf",
            "https://announcements.asx.com.au/asxpdf/20230906/pdf/abc123.pdf?date=20230906",
            "https://announcements.asx.com.au/asxpdf/20230906/pdf/abc123.pdf#date",
            "https://announcements.asx.com.au/other/20230906/abc123.pdf",
        ]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.check(source=dict(self.source, url=url))

    def test_release_mismatch(self):
        with self.assertRaises(ValueError):
            self.check(identity=dict(self.identity, publication_date="2023-09-07"))

    def test_signature_later_than_release(self):
        with self.assertRaises(ValueError):
            self.check(identity=dict(self.identity, document_issue_date="2023-09-07"))

    def test_after_cutoff(self):
        self.cutoff = "2023-09-05"
        with self.assertRaises(ValueError):
            self.check()

    def test_missing_date_or_markers(self):
        for text in ["", "signed 5 september 2022", "5 september 2023"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.check(text=text)
        with self.assertRaises(ValueError):
            self.check(identity=dict(self.identity, date_evidence={"page": 1, "markers": []}))

    def test_missing_or_wrong_roles(self):
        for field in ["publication_date_role", "date_evidence_role"]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(identity=dict(self.identity, **{field: "UNKNOWN"}))

    def test_integration_receipt_hash_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "source.pdf"
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_text((50, 50), "Signed 5 September 2023\nExample Project in Western Australia\nExample Limited")
            doc.save(pdf)
            doc.close()
            sha = filehash(pdf)
            source = dict(self.source, path="source.pdf", sha256=sha, asset_set="test",
                          evidence=[{"page": 1, "markers": ["Example Project"]}])
            identity = dict(self.identity, source_index=0, source_key="test",
                            name_marker="Example Project", state="WA", state_marker="Western Australia",
                            project_evidence={"page": 1, "markers": ["Example Project"]})
            candidate = dict(candidate_key="example", name="Example Project", aliases=[],
                             decision="ADMIT_PROJECT", reason="Test", country="AU", scope="Test",
                             sources=[source], identity=identity)
            ledger = root / "ledger.json"
            ledger.write_text(json.dumps(dict(version="reviewed-project-discovery-v1",
                cutoff=self.cutoff, acquired_through="2026-11-10", candidates=[candidate])), encoding="utf8")
            receipt = [{"url": self.source["url"], "document_sha256": sha, "status": "PDF_ACQUIRED"}]
            (root / "downloads.json").write_text(json.dumps(receipt), encoding="utf8")
            result = validate_discovery(ledger, {"test": root}, [], self.cutoff)
            self.assertEqual(result["sources"][sha]["publication_date"], "2023-09-06")
            self.assertEqual(result["sources"][sha]["document_issue_date"], "2023-09-05")
            self.assertEqual(result["sources"][sha]["publication_date_role"], "ASX_DATED_URL")
            receipt[0]["document_sha256"] = "wrong"
            (root / "downloads.json").write_text(json.dumps(receipt), encoding="utf8")
            with self.assertRaisesRegex(ValueError, "URL_HASH_NOT_CAPTURED"):
                validate_discovery(ledger, {"test": root}, [], self.cutoff)
            source["sha256"] = "wrong"
            candidate["sources"] = [source]
            cfg = json.loads(ledger.read_text())
            cfg["candidates"] = [candidate]
            ledger.write_text(json.dumps(cfg), encoding="utf8")
            with self.assertRaisesRegex(ValueError, "SOURCE_HASH_OR_PATH"):
                validate_discovery(ledger, {"test": root}, [], self.cutoff)


if __name__ == "__main__":
    unittest.main()
