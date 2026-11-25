import copy
import json
import unittest

from au_ree_v2.tabular import read_csv
from tools.compare_census_release import release
from tools.evaluate_normalization import BASELINE, PILOT, check_cases, check_controls, document_pages


class ReviewedNormalizationCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((PILOT / "case_review.json").read_bytes())
        cls.current = release(BASELINE)
        cls.refs, _ = document_pages(BASELINE, cls.fixture, None)
        cls.observations = read_csv(BASELINE / "resource_statement_observations.csv")

    def test_all_reviewed_cells_and_existing_positive_controls(self):
        findings = check_cases(BASELINE, self.current, self.fixture, self.refs)
        self.assertEqual(findings["held_by_class"], {"D1": 18, "E1": 14})
        self.assertEqual(check_controls(self.current, self.observations, self.fixture, self.refs), 5)

    def test_coverage_cannot_improve_by_omitting_or_reclassifying_reviewed_cells(self):
        cases = self.fixture["cases"]
        for changed in (cases[1:], [*cases, cases[0]]):
            with self.assertRaises(ValueError):
                check_cases(BASELINE, self.current, dict(self.fixture, cases=changed), self.refs)
        case = cases[0]
        states = dict(self.current["states"])
        states[case["project_id"], case["columns"][0]] = "NOT_APPLICABLE"
        with self.assertRaisesRegex(ValueError, "disagrees"):
            check_cases(BASELINE, dict(self.current, states=states), self.fixture, self.refs)

    def test_controls_require_the_same_project_value_and_source(self):
        bad = copy.deepcopy(self.fixture["controls"])
        bad[-1]["expected"] = 3225  # First five years in place of the whole-plan average.
        with self.assertRaisesRegex(ValueError, "differs"):
            check_controls(self.current, self.observations, dict(self.fixture, controls=bad), self.refs)
        bad[0]["project_id"] = bad[-1]["project_id"]
        with self.assertRaisesRegex(ValueError, "observation"):
            check_controls(self.current, self.observations, dict(self.fixture, controls=bad), self.refs)

    def test_wrong_source_or_cutoff_cannot_supply_a_page(self):
        with self.assertRaisesRegex(ValueError, "Unverified"):
            document_pages(BASELINE, dict(self.fixture, cutoff="2099-01-01"), None)
        fake = dict(self.fixture, documents={"0" * 64: {"1": {"markers": []}}})
        with self.assertRaisesRegex(ValueError, "Unverified"):
            document_pages(BASELINE, fake, None)
