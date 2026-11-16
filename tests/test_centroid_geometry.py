"""Live geometry regressions for the approved two-property spatial correction."""
import unittest
from shapely.geometry import Point,Polygon,mapping
from shapely.ops import unary_union
from au_ree_v2.spatial import summary_tenement_centroid


class TenementCentroidGeometry(unittest.TestCase):
    def calculate(self,polygons):
        features=[{'properties':{'tno':'EL'+str(i+1)},'geometry':mapping(p)} for i,p in enumerate(polygons)]
        return summary_tenement_centroid(features,'EPSG:7844',25000,'tno')

    def test_adjacent_polygons_centroid_is_inside_union(self):
        polygons=[Polygon([(140,-35),(140.01,-35),(140.01,-34.99),(140,-34.99)]),
                  Polygon([(140.01,-35),(140.02,-35),(140.02,-34.99),(140.01,-34.99)])]
        result=self.calculate(polygons)
        self.assertTrue(result['accepted'],result)
        self.assertEqual(result['location_method'],'TENEMENT_CENTROID')
        self.assertTrue(unary_union(polygons).covers(Point(result['longitude'],result['latitude'])))

    def test_gap_between_polygons_uses_largest_tenement(self):
        polygons=[Polygon([(140,-35),(140.02,-35),(140.02,-34.98),(140,-34.98)]),
                  Polygon([(140.08,-35),(140.09,-35),(140.09,-34.99),(140.08,-34.99)])]
        self.assertFalse(unary_union(polygons).covers(unary_union(polygons).centroid))
        result=self.calculate(polygons)
        self.assertTrue(result['accepted'],result)
        self.assertEqual(result['location_method'],'LARGEST_TENEMENT_CENTROID')
        self.assertTrue(polygons[0].covers(Point(result['longitude'],result['latitude'])))

    def test_c_shape_with_exterior_largest_centroid_is_rejected(self):
        polygon=Polygon([(140,-35),(140.06,-35),(140.06,-34.99),(140.01,-34.99),
                         (140.01,-34.95),(140.06,-34.95),(140.06,-34.94),(140,-34.94)])
        self.assertFalse(polygon.covers(polygon.centroid))
        result=self.calculate([polygon])
        self.assertFalse(result['accepted'])
        self.assertEqual(result['reason'],'LARGEST_TENEMENT_CENTROID_OUTSIDE_UNION')


if __name__=='__main__':unittest.main()
