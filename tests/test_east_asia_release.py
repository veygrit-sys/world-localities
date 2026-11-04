"""Published source receipts must not be mistaken for national completeness."""
import json
from pathlib import Path
import re
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import east_asia_sources as e


class ReleaseTests(unittest.TestCase):
    def read(self,name):return json.loads((ROOT/'releases/hierarchy/east-asia'/name).read_text())

    def test_scope_agrees_with_catalog_and_existing_address_profiles(self):
        scope=json.loads((ROOT/'address-points/EAST_ASIA_SCOPE.json').read_text())
        catalog=json.loads((ROOT/'releases/hierarchy/catalog.json').read_text())['regions']['east-asia']
        self.assertEqual(scope['country_codes'],list(e.SCOPE))
        self.assertEqual(scope['target_domains'],['administrative_divisions','address_streets','physical_roads','assigned_house_numbers'])
        self.assertEqual(catalog['scope_codes'],list(e.SCOPE))
        self.assertFalse(catalog['data_payloads_in_git'])
        sources=e.load_manifest()['sources']
        self.assertEqual(len(sources),17)
        for source in sources:
            self.assertRegex(source['sha256'],r'^[0-9a-f]{64}$')
            self.assertGreater(source['bytes'],0)

    def test_all_32_domains_keep_unverified_denominators_visible(self):
        value=self.read('coverage.json')
        self.assertEqual(value['remaining_pairs'],32)
        self.assertEqual(value['verified_complete_pairs'],0)
        self.assertFalse(value['deliverability_in_scope'])
        self.assertFalse(value['national_completeness_verified'])
        self.assertEqual(len(value['countries']),8)
        for country in value['countries']:
            self.assertEqual(len(country['domains']),4)
            for domain in country['domains'].values():
                self.assertFalse(domain['national_completeness_verified'])
                self.assertIsNone(domain['denominator'])
                self.assertIsNone(domain['coverage_ratio'])

    def test_every_source_and_native_projection_has_a_matching_full_replay(self):
        manifest=e.load_manifest();audit=self.read('source-audit.json');replay=self.read('source-replay.json')
        self.assertEqual(audit['implementation_sha256'],e.implementation_pins())
        self.assertEqual(replay['status'],'PASS')
        self.assertEqual(len(replay['sources']),17)
        by_id={s['source_id']:s for s in replay['sources']}
        for source in manifest['sources']:
            self.assertEqual(by_id[source['id']]['status'],'PASS')
            self.assertEqual(by_id[source['id']]['source_sha256'],source['sha256'])
        for proof in replay['sources']:
            if 'replay_implementation_sha256' in proof:
                self.assertEqual(proof['replay_implementation_sha256'],e.file_hash(ROOT/'scripts/east_asia_fast.py'))
                self.assertEqual(proof['pbf_field_reader_sha256'],e.file_hash(ROOT/'scripts/osm_pbf_lite.py'))
        projections=self.read('projections.json')
        self.assertEqual(len(projections['sources']),8)
        for report in projections['sources']:
            self.assertEqual(report['status'],'PASS')
            self.assertFalse(report['way_or_relation_geometry_assembled'])
            self.assertFalse(report['interpolation_expanded'])
            self.assertEqual(report['ordered_rows_sha256'],by_id[report['source']['id']]['ordered_rows_sha256'])

    def test_reference_grains_and_named_vs_unnamed_api_codes_are_distinct(self):
        cn=self.read('cn-explicit-parents.json');tw=self.read('tw-nlsc-replay.json')
        self.assertEqual(cn['source_date'],'2023-06-30')
        self.assertTrue(cn['streets_are_township_subdistrict_records_not_roads'])
        self.assertEqual(cn['unresolved_explicit_references'],{})
        self.assertEqual(cn['inconsistent_explicit_ancestors'],{})
        self.assertEqual(sum(cn['counts'].values()),665276)
        self.assertEqual(tw['named_village_references'],7781)
        self.assertEqual(tw['unnamed_village_references'],206)
        self.assertEqual(tw['responses'],391)
        self.assertFalse(tw['atomic_snapshot'])
        self.assertIsNone(tw['legal_effective_date'])

    def test_archive_pins_every_payload_and_excludes_private_machine_paths(self):
        archive=self.read('archive.json');proof=self.read('data-archive-verification.json')
        self.assertEqual(archive['format'],'zip-wrapped-byte-parts-v1')
        self.assertEqual(proof['status'],'PASS')
        self.assertFalse(archive['original_osm_pbf_in_distribution'])
        self.assertTrue(archive['native_selected_osm_objects_in_distribution'])
        for part in archive['parts']:
            self.assertLess(part['bytes'],512*1024*1024)
            self.assertRegex(part['sha256'],r'^[0-9a-f]{64}$')
        for code in archive['code_files']:
            self.assertEqual(code['sha256'],e.file_hash(ROOT/code['file']))
        payloads={row['file']:row for row in archive['contents']}
        for report in self.read('projections.json')['sources']:
            source=report['source'];self.assertEqual(payloads['data/'+source['path']]['sha256'],source['sha256'])
        for source in e.load_manifest()['sources']:
            if source['format']!='osm_pbf':self.assertEqual(payloads['data/'+source['path']]['sha256'],source['sha256'])
        folder=ROOT/'releases/hierarchy/east-asia'
        for path in folder.rglob('*'):
            if not path.is_file():continue
            self.assertNotIn(path.suffix,('.pbf','.zip','.csv'))
            text=path.read_text()
            for private in ['/workspace/','/dev/shm/','libfile-','upload_url','workspace_path']:
                self.assertNotIn(private,text,path.name)


if __name__=='__main__':unittest.main()
