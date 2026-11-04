import copy
import csv
import gzip
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import western_europe_sources as w
import osm_pbf_lite as pbf


class RegisterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def source(self, name, fmt, cc, members):
        path = self.root / name
        with zipfile.ZipFile(path, 'w') as archive:
            for member, data in members.items():
                archive.writestr(member, data)
        return {'id': cc + '-fixture', 'country': cc, 'format': fmt, 'path': name,
                'bytes': path.stat().st_size, 'sha256': w.sha256(path)}

    def manifest(self, source):
        return {'schema_version': 1, 'region': 'western-europe', 'scope_codes': list(w.SCOPE),
                'sources': [source], 'national_completeness_verified': False, 'deliverability_in_scope': False}

    def swiss(self):
        raw = 'ADR_EGAID;STR_ESID;ADR_NUMBER;COM_FOSNR;STN_LABEL;ADR_STATUS;ADR_OFFICIAL;ADR_EASTING;ADR_NORTHING\n'
        raw += '000123;0010;0007B;0001;Via Ångström;planned;false;2600000.123;1200000.456\n'
        return self.source('CH.zip', 'swiss_addresses_zip', 'CH', {'addresses.csv': raw})

    def test_source_values_ids_and_unverified_flags_survive(self):
        source = self.swiss()
        row = next(w.records(source, self.root))
        self.assertEqual(row['source_id'], '000123')
        self.assertEqual(row['number'], '0007B')
        self.assertEqual(row['admin_code'], '0001')
        self.assertEqual(row['street_names'], {'und': 'Via Ångström'})
        self.assertEqual(row['status'], 'planned')
        self.assertEqual(row['official'], 'false')
        self.assertEqual(row['coordinates']['source_crs'], 'EPSG:2056')
        self.assertEqual(row['raw']['ADR_EASTING'], '2600000.123')
        self.assertEqual(row['source_sha256'], source['sha256'])

    def test_planned_address_is_not_current_and_numbers_are_exact_strings(self):
        source = self.swiss()
        manifest = self.manifest(source)
        self.assertEqual(len(w.search(manifest, self.root, 'CH', number='0007B')['results']), 1)
        self.assertFalse(w.search(manifest, self.root, 'CH', number='7')['results'])
        self.assertFalse(w.search(manifest, self.root, 'CH', current_only=True)['results'])
        with self.assertRaises(ValueError):
            w.search(manifest, self.root, 'CH', number=7)

    def test_raw_source_tampering_is_rejected(self):
        source = self.swiss()
        with (self.root / source['path']).open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'Source bytes differ'):
            w.verify_pin(source, self.root)

    def test_paths_cannot_escape_including_symlinks(self):
        for path in ('../outside.zip', '/tmp/outside.zip'):
            with self.assertRaises(ValueError):
                w.source_path(self.root, {'path': path})
        (self.root / 'link').symlink_to(self.root.parent)
        with self.assertRaises(ValueError):
            w.source_path(self.root, {'path': 'link/outside.zip'})

    def test_manifest_rejects_scope_and_completeness_inflation(self):
        source = self.swiss()
        original = self.manifest(source)
        for changed in [dict(original, deliverability_in_scope=True),
                        dict(original, national_completeness_verified=True),
                        dict(original, scope_codes=['CH']), dict(original, sources=[source, source])]:
            path = self.root / 'manifest.json'; path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                w.load_manifest(path)
        bad = copy.deepcopy(original);bad['sources'][0]['country'] = 'LU'
        path.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError, 'jurisdiction'):
            w.load_manifest(path)

    def test_unacquired_country_is_not_a_successful_country_audit(self):
        result = w.audit(self.manifest(self.swiss()), self.root, 'DE')
        self.assertEqual(result['status'], 'NO_ACCEPTED_SOURCE')
        self.assertFalse(result['national_completeness_verified'])

    def test_acceptance_replay_rejects_changed_report_and_implementation(self):
        manifest = self.manifest(self.swiss())
        accepted = w.audit(manifest, self.root)
        self.assertEqual(w.replay(manifest, self.root, accepted)['source_row_replay'], 'PASS')
        changed = copy.deepcopy(accepted)
        changed['source_reports'][0]['counts']['address'] += 1
        with self.assertRaisesRegex(ValueError, 'replay differs'):
            w.replay(manifest, self.root, changed)
        changed = copy.deepcopy(accepted); changed['implementation_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Implementation'):
            w.replay(manifest, self.root, changed)

    def test_duplicate_zip_members_and_malformed_csv_are_rejected(self):
        source = self.source('bad.zip', 'swiss_streets_zip', 'CH', {'a.csv': 'a;a\n1;2\n'})
        with self.assertRaises(ValueError):
            list(w.records(source, self.root))
        source = self.source('short.zip', 'swiss_streets_zip', 'CH', {'a.csv': 'a;b\n1\n'})
        with self.assertRaises(ValueError):
            list(w.records(source, self.root))

    def test_belgian_languages_and_new_crs_are_preserved(self):
        row = {'address_id':'001','house_number':'12-14','street_id':'009','municipality_id':'21001',
               'region_code':'BE-BRU','EPSG:4326_lat':'50.8','EPSG:4326_lon':'4.3',
               'EPSG:3812_x':'600000','EPSG:3812_y':'600000','status':'current',
               'streetname_fr':'Rue A','streetname_nl':'A-straat','streetname_de':'','box_number':'0002'}
        stream = io.StringIO(); writer=csv.DictWriter(stream,fieldnames=list(row));writer.writeheader();writer.writerow(row)
        source = self.source('BE.zip','best_addresses_zip','BE',{'addresses.csv':stream.getvalue()})
        actual=next(w.records(source,self.root))
        self.assertEqual(actual['source_id'],'BE-BRU:001')
        self.assertEqual(actual['number'],'12-14')
        self.assertEqual(actual['box_number'],'0002')
        self.assertEqual(actual['street_names'],{'nl':'A-straat','fr':'Rue A','de':''})
        self.assertNotIn('en',actual['street_names'])

    def test_ban_overseas_rows_do_not_become_metropolitan_france(self):
        path=self.root/'ban.csv.gz'
        with gzip.open(path,'wt') as stream:
            stream.write('id;numero;rep;nom_voie;code_insee;certification_commune\n')
            stream.write('x;0007;bis;Rue X;75056;1\n')
            stream.write('y;2;;Rue Y;97101;0\n')
        source={'id':'FR-test','country':'FR','format':'ban_national_csv_gz','path':path.name,
                'bytes':path.stat().st_size,'sha256':w.sha256(path)}
        rows=list(w.records(source,self.root))
        self.assertEqual([r['country'] for r in rows],['FR','GP'])
        self.assertEqual(rows[0]['number'],'0007')
        self.assertEqual(rows[1]['kind'],'outside_scope_address')
        self.assertEqual(len(w.search(self.manifest(source),self.root,'FR')['results']),1)

    def test_caclr_null_flags_and_truncated_dbf_fail_explicitly(self):
        self.assertIsNone(w.fixed_value('1234?',1,4,5))
        self.assertEqual(w.fixed_value('0001 ',1,4,5),'0001')
        with self.assertRaises(ValueError):list(w.dbf_rows(b'short'))

    def test_region_uses_legacy_group_without_reclassifying_m49(self):
        self.assertEqual(len(w.SCOPE),11)
        self.assertEqual(len(w.M49),9)
        self.assertNotIn('GB',w.M49)
        self.assertNotIn('IE',w.M49)


def vi(value):
    out=bytearray()
    while value>=128:out.append((value&127)|128);value>>=7
    out.append(value);return bytes(out)


def fld(number,value):
    return vi(number*8+2)+vi(len(value))+value if isinstance(value,bytes) else vi(number*8)+vi(value)


class PbfTests(unittest.TestCase):
    def test_signed_and_delta_varints_and_truncation(self):
        self.assertEqual(list(pbf.packed(vi(4)+vi(1)+vi(6),True,True)),[2,1,4])
        with self.assertRaises(ValueError):pbf.varint(b'\x80')
        with self.assertRaises(ValueError):list(pbf.fields(b'\x0a\x03x'))

    def test_small_pbf_export_preserves_number_and_source_topology(self):
        strings=['','addr:housenumber','0007B','highway','residential','name','Test road']
        string_table=b''.join(fld(1,s.encode()) for s in strings)
        node1=fld(1,2)+fld(2,vi(1))+fld(3,vi(2))+fld(8,20)+fld(9,40)
        node2=fld(1,4)+fld(8,22)+fld(9,42)
        way=fld(1,3)+fld(2,vi(3)+vi(5))+fld(3,vi(4)+vi(6))+fld(8,vi(2)+vi(2))
        primitive=fld(1,string_table)+fld(2,fld(1,node1)+fld(1,node2)+fld(3,way))
        blob=fld(1,primitive);header=fld(1,b'OSMData')+fld(3,len(blob))
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/'small.pbf';raw.write_bytes(struct.pack('>I',len(header))+header+blob)
            receipt={'id':'MC-fixture','country':'MC','bytes':raw.stat().st_size,'sha256':w.sha256(raw)}
            output=Path(tmp)/'out.gz';report=pbf.export(raw,receipt,output)
            with gzip.open(output,'rt') as stream:rows=[json.loads(line) for line in stream]
            self.assertEqual(rows[0]['tags']['addr:housenumber'],'0007B')
            self.assertEqual(rows[1]['source_topology']['nodes'],[1,2])
            self.assertEqual(rows[1]['geometry']['type'],'LineString')
            self.assertEqual(report['counts']['active_road_ways'],1)
            self.assertFalse(report['interpolation_expanded'])


if __name__ == '__main__':
    unittest.main()
