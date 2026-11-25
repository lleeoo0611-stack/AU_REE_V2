"""Live geometry regressions for the approved two-property spatial correction."""
import unittest
from shapely.geometry import Point,Polygon,mapping,shape
from shapely.ops import unary_union
from au_ree_v2.spatial import summary_tenement_centroid, _arcgis_tenement_features, _wa_bound_features


class TenementCentroidGeometry(unittest.TestCase):
    def test_arcgis_preserves_disjoint_parts_and_holes_and_checks_inventory(self):
        rings = [
            [[0, 0], [8, 0], [8, 8], [0, 8], [0, 0]],
            [[1, 1], [2, 1], [2, 2], [1, 2], [1, 1]],
            [[10, 0], [11, 0], [11, 1], [10, 1], [10, 0]],
        ]
        binding = dict(source_crs='EPSG:4326', tenement_ids=['EPM 12'], id_field='title',
                       required_attributes=dict(status='Granted'))
        data = dict(inventory=dict(complete=True, count=1, scope='global'),
                    spatialReference=dict(wkid=4326),
                    features=[dict(attributes=dict(title='EPM12', status='Granted'),
                                   geometry=dict(rings=rings))])
        selected = _arcgis_tenement_features(data, binding)
        polygon = shape(selected[0]['geometry'])
        self.assertEqual(polygon.geom_type, 'MultiPolygon')
        self.assertEqual(polygon.area, 64)
        self.assertFalse(polygon.covers(Point(1.5, 1.5)))
        for invalid in [
            dict(inventory=dict(complete=False, count=1, scope='global')),
            dict(inventory=dict(complete=True, count=2, scope='global')),
            dict(spatialReference=dict(wkid=4283)),
            dict(exceededTransferLimit=True),
        ]:
            with self.subTest(invalid=invalid):
                self.assertEqual(_arcgis_tenement_features(dict(data, **invalid), binding), [])
        self.assertEqual(_arcgis_tenement_features(data, dict(binding, required_attributes=dict(status='Expired'))), [])

    def test_mixed_granted_and_application_require_both_matching_official_features(self):
        ring = [[140, -35], [140.01, -35], [140, -34.99], [140, -35]]
        def feature(title, status):
            return dict(attributes=dict(title=title, holder='GDM', status=status), geometry=dict(rings=[ring]))
        granted = feature('EPM 22', 'Granted')
        application = feature('EPM 43', 'Application')
        data = dict(inventory=dict(complete=True, count=2, scope='global'),
                    spatialReference=dict(wkid=4326), features=[granted, application])
        binding = dict(source_crs='EPSG:4326', tenement_ids=['EPM 22', 'EPM 43'], id_field='title',
                       required_attributes=dict(holder='GDM'), attributes_by_title={
                           'EPM 22': dict(status='Granted'), 'EPM 43': dict(status='Application')})
        self.assertEqual(len(_arcgis_tenement_features(data, binding)), 2)
        for invalid in ([granted, granted], [granted, feature('EPM 43', 'Granted')], [granted]):
            with self.subTest(features=invalid):
                current = dict(data, inventory=dict(data['inventory'], count=len(invalid)), features=invalid)
                self.assertEqual(_arcgis_tenement_features(current, binding), [])

    def test_archived_title_requires_one_matching_record_and_holder_for_every_title(self):
        first = dict(properties=dict(FMT_TENID='E 15/1495', HOLDER1='CUFE LIMITED', TENSTATUS='LIVE'))
        second = dict(properties=dict(FMT_TENID='M 15/1841', HOLDER1='CUFE LTD', TENSTATUS='LIVE'))
        selected = {('E', 15, 1495): [first], ('M', 15, 1841): [second]}
        binding = dict(tenement_ids=['E 15/1495', 'M 15/1841'], attributes_by_title={
            'E 15/1495': dict(HOLDER1='CUFE LIMITED', TENSTATUS='LIVE'),
            'M 15/1841': dict(HOLDER1='CUFE LTD', TENSTATUS='LIVE')})
        self.assertEqual(_wa_bound_features(selected, binding), [first, second])
        for mismatched in ([first, first], [], [second]):
            with self.subTest(mismatched=mismatched):
                self.assertEqual(_wa_bound_features({**selected, ('E', 15, 1495): mismatched}, binding), [])
        self.assertEqual(_wa_bound_features(selected, dict(binding, tenement_ids=['E 15/1495'])), [])

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
