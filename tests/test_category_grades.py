"""Regression checks for the resource-grade comparison pilot."""
import copy
import json
import unittest
from decimal import Decimal

from tools.category_grades import CATEGORY, MASS_RULE, weighted_grade


class CategoryGradeTests(unittest.TestCase):
    def setUp(self):
        self.table = {
            "INDICATED": (Decimal(160), Decimal(1700), {"Nd2O3": Decimal(310)}),
            "INFERRED": (Decimal(1500), Decimal(1700), {"Nd2O3": Decimal(280)}),
        }
        self.parts = [
            {"category": name, "cutoff_treo_ppm": 1000, "ore_mt": int(tonnes),
             "treo_ppm": int(treo), "oxide_ppm": int(grades["Nd2O3"])}
            for name, (tonnes, treo, grades) in self.table.items()
        ]

    def observation(self, parts):
        return {"basis": "Nd2O3", "variable": "reported_resource_contained_nd2o3_kt", "value": "469.6",
                "material_basis": "RESOURCE_CONTAINED_OXIDE_MASS_KT", "category": CATEGORY, "unit": "kt",
                "source_transform": json.dumps({"rule": MASS_RULE, "cutoff_treo_ppm": 1000, "categories": parts})}

    def test_divides_only_by_sum_of_admitted_categories(self):
        grade = weighted_grade(self.observation(self.parts), self.table)
        self.assertEqual(Decimal(469600) / 1660, grade)
        self.assertNotEqual(Decimal(469600) / 1700, grade)

    def test_rejects_wrong_cutoff_duplicate_category_and_wrong_ore(self):
        for field, value in (("cutoff_treo_ppm", 800), ("category", "INDICATED"),
                             ("ore_mt", 1540), ("oxide_ppm", 310)):
            with self.subTest(field=field):
                parts = copy.deepcopy(self.parts)
                parts[1][field] = value
                with self.assertRaises(ValueError):
                    weighted_grade(self.observation(parts), self.table)

    def test_rejects_hm_and_conflicting_total_mass(self):
        for field, value in (("material_basis", "HM_ONLY"), ("value", "470")):
            with self.subTest(field=field):
                observation = self.observation(self.parts)
                observation[field] = value
                with self.assertRaises(ValueError):
                    weighted_grade(observation, self.table)
