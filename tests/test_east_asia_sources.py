"""Source integrity, granularity and replay tests using local fixtures."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import east_asia_sources as e
import east_asia_projection as p
import east_asia_query as q
import east_asia_fast as f
import tw_nlsc_reference as n


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def pin(self, content, name='source.csv', fmt='csv', **extra):
        path = self.root / name; path.write_bytes(content)
        return dict(id='JP-fixture', country='JP', format=fmt, role='fixture', path=name,
                    bytes=len(content), sha256=hashlib.sha256(content).hexdigest(), **extra)

    def test_scope_matches_existing_eight_profiles_and_never_claims_complete(self):
        value = e.load_manifest()
        self.assertEqual(set(value['scope_codes']), {'CN','HK','JP','KP','KR','MN','MO','TW'})
        self.assertFalse(value['national_completeness_verified'])
        self.assertFalse(value['deliverability_in_scope'])
        for mutate in [lambda m: m.update(national_completeness_verified=True),
                       lambda m: m.update(deliverability_in_scope=True),
                       lambda m: m['sources'][0].update(country='US'),
                       lambda m: m['sources'].pop(0),
                       lambda m: m['sources'][0].update(url='https://download.geofabrik.de/asia/china-latest.osm.pbf')]:
            changed = copy.deepcopy(value); mutate(changed)
            path = self.root/'manifest.json';path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):e.load_manifest(path)

    def test_traversal_and_symlink_escape_fail(self):
        for name in ['../secret','/etc/passwd','x/../../secret','x\\secret']:
            with self.assertRaises(ValueError):e.safe_path(self.root,name)
        (self.root/'escape').symlink_to('/etc')
        with self.assertRaises(ValueError):e.safe_path(self.root,'escape/passwd')

    def test_source_hash_and_size_are_checked_before_query(self):
        source=self.pin(b'id,number\n001,007\n')
        (self.root/'source.csv').write_bytes(b'id,number\n001,008\n')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):e.search(source,self.root)

    def test_original_strings_duplicate_rows_and_blank_fields_survive(self):
        source=self.pin('id,number,name,optional\n001,007,札幌,\n001,007,札幌,\n'.encode(),id_field='id')
        result=e.search(source,self.root,identity='001',limit=2)
        self.assertEqual(len(result['results']),2)
        self.assertEqual(result['results'][0]['raw']['number'],'007')
        audit=e.audit_one(source,self.root)
        self.assertEqual(audit['counts']['observations'],2)
        self.assertEqual(audit['metadata']['empty_fields']['optional'],2)
        self.assertFalse(audit['metadata']['source_ids_strictly_increasing'])

    def test_table_role_is_not_reclassified_by_query(self):
        source=self.pin(b'city,site_id,road\nA,B,road\n')
        with self.assertRaisesRegex(ValueError,'grain'):e.search(source,self.root,kind='address')

    def test_json_explicit_parents_are_kept_and_not_derived_from_prefix(self):
        source=self.pin(b'[{"code":"001","provinceCode":"88","name":"name"}]','codes.json','json',id_field='code')
        self.assertEqual(e.search(source,self.root,identity='001')['results'][0]['raw']['provinceCode'],'88')
        self.assertNotIn('parent_id',e.search(source,self.root)['results'][0])

    def test_cn_parent_audit_detects_missing_and_contradicting_source_fields(self):
        rows=[{'code':'88','name':'province'}, {'code':'44','name':'city','provinceCode':'88'},
              {'code':'002','cityCode':'44','provinceCode':'88'},
              {'code':'003','areaCode':'002','cityCode':'44','provinceCode':'88'},
              {'code':'999','streetCode':'003','areaCode':'002','cityCode':'44','provinceCode':'88'}]
        sources=[]
        for level,row in zip(e.CN_LEVELS,rows):
            source=self.pin(json.dumps([row]).encode(),level+'.json','json',id_field='code')
            source['id']='CN-statistical-'+level;sources.append(source)
        manifest={'sources':sources}
        report=e.cn_reference_audit(manifest,self.root)
        self.assertEqual(report['unresolved_explicit_references'],{})
        chain=e.cn_parents(manifest,self.root,'CN-statistical-villages','999')
        self.assertEqual([r['raw']['code'] for r in chain['chain']],['999','003','002','44','88'])
        rows[-1]['provinceCode']='77'
        changed=self.pin(json.dumps([rows[-1]]).encode(),'villages.json','json',id_field='code')
        changed['id']='CN-statistical-villages';sources[-1]=changed
        report=e.cn_reference_audit(manifest,self.root)
        self.assertEqual(report['unresolved_explicit_references'],{'villages.provinceCode':1})
        self.assertTrue(report['inconsistent_explicit_ancestors'])

    def test_bad_csv_width_duplicate_headers_and_json_shape_fail(self):
        for data in [b'a,b\n1\n',b'a,b\n1,2,3\n',b'a,a\n1,2\n']:
            with self.assertRaises(ValueError):e.audit_one(self.pin(data),self.root)
        with self.assertRaises(ValueError):e.audit_one(self.pin(b'{}','codes.json','json'),self.root)

    def test_zip_member_selection_is_exact_and_avoids_extraction(self):
        path=self.root/'data.zip'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('a.csv','id,name\n001,name\n');z.writestr('b.csv','id,name\n002,name\n')
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            with e.csv_reader(path): pass

    def test_zip_unicode_csv_works_without_temporary_extraction(self):
        path=self.root/'data.zip'
        with zipfile.ZipFile(path,'w') as z:z.writestr('nested/source.csv','id,name\n001,臺北\n')
        source={'id':'TW-test','country':'TW','format':'csv_zip','role':'reference','path':'data.zip','bytes':path.stat().st_size,'sha256':e.file_hash(path)}
        self.assertEqual(e.search(source,self.root,text='臺北')['results'][0]['raw']['id'],'001')

    def test_full_source_replay_rejects_rehashed_changed_rows(self):
        source=self.pin(b'id,number\n001,007\n')
        manifest={'sources':[source]};accepted=e.audit(manifest,self.root)
        self.assertEqual(e.replay(manifest,self.root,accepted)['status'],'PASS')
        changed=self.pin(b'id,number\n001,008\n')
        with self.assertRaisesRegex(ValueError,'replay differs'):e.replay({'sources':[changed]},self.root,accepted)
        changed=copy.deepcopy(accepted);changed['implementation_sha256']['east_asia_sources.py']='0'*64
        with self.assertRaisesRegex(ValueError,'implementation'):e.replay(manifest,self.root,changed)

    def test_osm_preserves_numbers_lifecycle_version_and_ordered_references(self):
        import osmium
        path=self.root/'fixture.osm.pbf'
        with osmium.SimpleWriter(str(path)) as writer:
            writer.add_node(osmium.osm.mutable.Node(id=1,version=2,location=(139,35),tags={'addr:housenumber':'007','addr:street':'路'}))
            writer.add_way(osmium.osm.mutable.Way(id=2,version=3,nodes=[1,9],tags={'highway':'residential','name':'道路'}))
            writer.add_way(osmium.osm.mutable.Way(id=3,nodes=[1,9],tags={'highway':'construction','construction':'residential'}))
            writer.add_way(osmium.osm.mutable.Way(id=4,nodes=[1,9],tags={'addr:interpolation':'even'}))
        rows=list(e.osm_rows(path))
        self.assertEqual(len(rows),4)
        self.assertEqual(rows[0]['tags']['addr:housenumber'],'007')
        self.assertEqual(rows[0]['version'],2)
        self.assertEqual(rows[1]['nodes'],['1','9'])
        self.assertEqual(rows[2]['classification']['road_state'],'construction')
        self.assertFalse(rows[2]['classification']['named_road'])
        self.assertFalse(rows[3]['classification']['house_number'])
        self.assertNotIn('coordinates',rows[1])

    def test_native_projection_matches_source_and_rejects_wrong_source_pin(self):
        import osmium
        path=self.root/'original.osm.pbf'
        with osmium.SimpleWriter(str(path)) as writer:
            writer.add_node(osmium.osm.mutable.Node(id=1,version=2,location=(139,35),tags={'addr:housenumber':'007'}))
            writer.add_node(osmium.osm.mutable.Node(id=2,location=(140,36)))
            writer.add_way(osmium.osm.mutable.Way(id=3,nodes=[1,2],tags={'highway':'residential'}))
        source={'id':'OSM-JP','country':'JP','format':'osm_pbf','role':'supplementary','path':path.name,
                'url':'https://download.geofabrik.de/asia/japan-261020.osm.pbf','bytes':path.stat().st_size,'sha256':e.file_hash(path)}
        accepted=e.audit_one(source,self.root)
        report=p.export(source,self.root,self.root/'projections/JP.osm.pbf',accepted)
        self.assertEqual(report['status'],'PASS')
        self.assertEqual(report['counts']['observations'],2)
        self.assertFalse(report['untagged_dependency_nodes_copied'])
        result=p.search({'sources':[source]},{'sources':[report]},self.root,'OSM-JP',kind='road')
        self.assertEqual(result['results'][0]['nodes'],['1','2'])
        self.assertEqual(result['original_source_sha256'],source['sha256'])
        exact=q.lookup(source,self.root,['osm:node:1','osm:way:3','osm:node:2'])
        self.assertEqual(exact['missing_ids'],['osm:node:2'])
        self.assertEqual(exact['results'],list(e.osm_rows(path)))
        with self.assertRaisesRegex(ValueError,'complete positive'):q.lookup(source,self.root,['3'])
        changed=copy.deepcopy(report);changed['source']['original_source_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'pinned original'):p.search({'sources':[source]},{'sources':[changed]},self.root,'OSM-JP')
        bad=copy.deepcopy(accepted);bad['source_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'pin differs'):p.export(source,self.root,self.root/'bad.osm.pbf',bad)

    def test_native_projection_rejects_audited_row_digest_mismatch(self):
        import osmium
        path=self.root/'original.osm.pbf'
        with osmium.SimpleWriter(str(path)) as writer:writer.add_node(osmium.osm.mutable.Node(id=1,location=(139,35),tags={'addr:housenumber':'1'}))
        source={'id':'OSM-JP','country':'JP','format':'osm_pbf','role':'supplementary','path':path.name,'url':'https://example.invalid/source','bytes':path.stat().st_size,'sha256':e.file_hash(path)}
        accepted=e.audit_one(source,self.root);accepted['ordered_rows_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'ordered_rows'):p.export(source,self.root,self.root/'bad.osm.pbf',accepted)

    def test_native_prefilter_is_exhaustive_for_custom_address_keys_and_lifecycle(self):
        import osmium
        path=self.root/'original.osm.pbf'
        with osmium.SimpleWriter(str(path)) as writer:
            writer.add_node(osmium.osm.mutable.Node(id=1,location=(139,35),tags={'addr:unusual:source':'raw'}))
            writer.add_node(osmium.osm.mutable.Node(id=2,location=(139,35),tags={'place':'village'}))
            writer.add_way(osmium.osm.mutable.Way(id=3,nodes=[1,2],tags={'abandoned:highway':'track'}))
            writer.add_way(osmium.osm.mutable.Way(id=4,nodes=[1,2],tags={'building':'yes'}))
            writer.add_relation(osmium.osm.mutable.Relation(id=5,members=[('w',3,'outer')],tags={'boundary':'administrative','admin_level':'8'}))
        source={'id':'OSM-JP','country':'JP','format':'osm_pbf','role':'supplementary','path':path.name,
                'url':'https://example.invalid/source','bytes':path.stat().st_size,'sha256':e.file_hash(path),
                'licence':'ODbL-1.0','licence_url':'https://www.openstreetmap.org/copyright','attribution':'OpenStreetMap contributors'}
        expected=e.audit_one(source,self.root)
        actual,proof,projection=f.audit_native(source,self.root,self.root/'native.osm.pbf',expected)
        self.assertEqual(actual,expected)
        self.assertEqual(proof['status'],'PASS')
        self.assertIn('addr:unusual:source',proof['candidate_keys'])
        self.assertFalse(proof['independent_parser_implementation'])
        self.assertEqual(projection['counts']['observations'],3)
        actual,_,projection=f.audit_native(source,self.root)
        self.assertEqual(actual,expected)
        self.assertIsNone(projection)
        bad=copy.deepcopy(expected);bad['counts']['observations']=4
        with self.assertRaisesRegex(ValueError,'differs'):f.audit_native(source,self.root,accepted=bad)

    def test_native_key_inventory_rejects_truncated_or_oversized_blocks(self):
        import struct
        for content in [b'\0\0\0',struct.pack('>I',65537),b'\0\0\0\0']:
            path=self.root/'invalid.pbf';path.write_bytes(content)
            with self.assertRaises(ValueError):f.candidate_keys(path)


class NLSCTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def snapshot(self):
        specs=[('county',None,b'<countyItems><countyItem><countycode>A</countycode><countyname>city</countyname><countycode01>99</countycode01></countyItem></countyItems>'),
               ('town','county:A',b'<townItems><townItem><towncode>001</towncode><towncode01>A01</towncode01><townname>town</townname></townItem></townItems>'),
               ('village','town:001',b'<villages><village><villageId>XYZ</villageId><villageName/></village></villages>')]
        pins=[]
        for i,(level,parent,data) in enumerate(specs):
            path=self.root/f'{i}.xml';path.write_bytes(data)
            pins.append({'path':path.name,'level':level,'parent_id':parent,'bytes':len(data),'sha256':e.file_hash(path)})
        return {'responses':pins}

    def test_explicit_request_parents_and_unnamed_codes_survive(self):
        value=n.build(self.root,self.snapshot())
        self.assertEqual(value['records'][2]['parent_id'],'town:001')
        self.assertEqual(value['records'][2]['id'],'village:XYZ')
        self.assertEqual(value['records'][2]['record_kind'],'unnamed_api_reference')
        self.assertEqual(value['counts']['unnamed_village'],1)
        self.assertEqual(value['orphans'],0)

    def test_missing_response_parent_binding_and_changed_xml_fail(self):
        manifest=self.snapshot()
        with self.assertRaisesRegex(ValueError,'request coverage'):n.build(self.root,{'responses':manifest['responses'][:-1]})
        changed=copy.deepcopy(manifest);changed['responses'][2]['parent_id']='town:999'
        with self.assertRaisesRegex(ValueError,'parent'):n.build(self.root,changed)
        (self.root/'2.xml').write_bytes(b'<villages/>')
        with self.assertRaisesRegex(ValueError,'changed'):n.build(self.root,manifest)

    def test_xml_schema_dtd_and_truncation_fail(self):
        for data in [b'<!DOCTYPE x><villages/>',b'<countyItems/>',b'<villages><village>',b'<villages><village><x>1</x></village></villages>']:
            with self.assertRaises((ValueError,n.ET.ParseError)):n.parse(data,'village')


if __name__=='__main__':unittest.main()
