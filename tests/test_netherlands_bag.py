import copy
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'address-points/adapters'))
import netherlands_bag as n
import westerneurope as adapter


SNAPSHOT = '2026-10-08'


def document(objects, country=True, snapshot=SNAPSHOT):
    return (f'<e:bagStand xmlns:e="{n.EXTRACT_NS}" xmlns:o="{n.OBJECT_NS}" '
            f'xmlns:h="{n.HISTORY_NS}" xmlns:r="{n.REF_NS}" xmlns:s="{n.SELECT_NS}" '
            f'xmlns:sl="{n.STAND_NS}"><e:bagInfo>'
            + ('<s:Gebied-NLD/>' if country else '<s:Gebied-GEM/>')
            + f'<s:StandTechnischeDatum>{snapshot}</s:StandTechnischeDatum></e:bagInfo><sl:standBestand>'
            + ''.join('<sl:stand><e:bagObject>' + obj + '</e:bagObject></sl:stand>' for obj in objects)
            + '</sl:standBestand></e:bagStand>').encode()


def history(extra=''):
    return ('<o:voorkomen><h:Voorkomen><h:voorkomenidentificatie>1</h:voorkomenidentificatie>'
            '<h:beginGeldigheid>2020-01-01</h:beginGeldigheid>'
            '<h:tijdstipRegistratie>2020-01-02T12:00:00</h:tijdstipRegistratie>'
            + extra + '<h:BeschikbaarLV><h:tijdstipRegistratieLV>2020-01-02T12:01:00</h:tijdstipRegistratieLV>'
            '</h:BeschikbaarLV></h:Voorkomen></o:voorkomen>')


def number(extra=''):
    return ('<o:Nummeraanduiding><o:identificatie domein="NL.IMBAG.Nummeraanduiding">0001200000000001</o:identificatie>'
            '<o:huisnummer>007</o:huisnummer><o:huisletter>b</o:huisletter><o:huisnummertoevoeging>02</o:huisnummertoevoeging>'
            '<o:postcode>1234AB</o:postcode><o:typeAdresseerbaarObject>Ligplaats</o:typeAdresseerbaarObject>'
            '<o:status>Naamgeving uitgegeven</o:status><o:geconstateerd>J</o:geconstateerd>'
            '<o:documentdatum>2020-01-01</o:documentdatum><o:documentnummer>ABC</o:documentnummer>'
            + history(extra) + '<o:ligtAan><r:OpenbareRuimteRef>0001300000000001</r:OpenbareRuimteRef></o:ligtAan>'
            '</o:Nummeraanduiding>')


def space(typ='Weg'):
    return ('<o:OpenbareRuimte><o:identificatie>0001300000000001</o:identificatie><o:naam>Ångströmstraat</o:naam>'
            f'<o:type>{typ}</o:type><o:status>Naamgeving uitgegeven</o:status><o:geconstateerd>N</o:geconstateerd>'
            '<o:documentdatum>2020-01-01</o:documentdatum><o:documentnummer>XYZ</o:documentnummer>'
            '<o:ligtIn><r:WoonplaatsRef>0001</r:WoonplaatsRef></o:ligtIn>' + history() + '</o:OpenbareRuimte>')


class BagContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def pin(self, data, role='number_designations', name='NUM.zip'):
        path = self.root / name
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('part.xml', data)
        return {'id': 'NL-test-' + role, 'country': 'NL', 'role': role, 'format': 'bag_xml_zip',
                'path': name, 'bytes': path.stat().st_size, 'sha256': n.shared.sha256(path)}

    def rows(self, source):
        return list(n.records(source, self.root, SNAPSHOT))

    def test_lexical_ids_number_letter_addition_and_object_type_survive(self):
        row = self.rows(self.pin(document([number()])))[0]
        self.assertEqual(row['source_id'], '0001200000000001')
        self.assertEqual((row['number'], row['house_letter'], row['number_addition']), ('007', 'b', '02'))
        self.assertEqual(row['addressable_object_type'], 'Ligplaats')
        self.assertEqual(row['geconstateerd'], 'J')
        self.assertTrue(row['registry_open_at_snapshot'])
        self.assertEqual(row['raw']['identificatie/@attributes']['domein'], 'NL.IMBAG.Nummeraanduiding')
        self.assertNotIn('deliverability', row)

    def test_closed_registered_future_and_withdrawn_versions_stay_out_of_open_filter(self):
        for extra in ('<h:eindGeldigheid>2026-10-08</h:eindGeldigheid>',
                      '<h:eindRegistratie>2021-01-01T00:00:00</h:eindRegistratie>',
                      '<h:tijdstipInactief>2021-01-01T00:00:00</h:tijdstipInactief>'):
            source = self.pin(document([number(extra)]))
            self.assertFalse(self.rows(source)[0]['registry_open_at_snapshot'])
        for old, new in (('2020-01-01</h:begin', '2027-01-01</h:begin'),
                         ('Naamgeving uitgegeven', 'Naamgeving ingetrokken')):
            self.assertFalse(self.rows(self.pin(document([number().replace(old, new)])))[0]['registry_open_at_snapshot'])

    def test_country_date_namespace_type_and_duplicate_fields_are_checked(self):
        cases = [document([number()], country=False), document([number()], snapshot='2026-10-09'),
                 document([number()]).replace(n.OBJECT_NS.encode(), b'https://example.invalid/objects'),
                 document([space()]), document([number().replace('<o:huisnummer>007</o:huisnummer>',
                    '<o:huisnummer>007</o:huisnummer><o:huisnummer>8</o:huisnummer>')])]
        for data in cases:
            with self.assertRaises(ValueError):
                self.rows(self.pin(data))

    def test_nonroad_public_spaces_are_kept_separately(self):
        source = self.pin(document([space('Water')]), 'public_spaces')
        row = self.rows(source)[0]
        self.assertEqual(row['kind'], 'named_area')
        self.assertEqual(row['public_space_type'], 'Water')
        self.assertEqual(row['street_names'], {'nl': 'Ångströmstraat'})

    def test_not_bag_and_inactive_records_are_never_current_main_addresses(self):
        for role, category in [('not_bag', 'not_bag'), ('inactive', 'inactive')]:
            row = list(n.xml_records(io.BytesIO(document([number()])),
                                    {'id': 'NL-'+role, 'country': 'NL', 'sha256': 'a'*64, 'role': role},
                                    'part.xml', SNAPSHOT, category))[0]
            self.assertEqual(row['kind'], category + '_address_history')
            self.assertFalse(row['registry_open_at_snapshot'])

    def test_dtd_truncated_and_corrupt_xml_fail(self):
        for data in [b'<!DOCTYPE e [<!ENTITY x "x">]>' + document([number()]), document([number()])[:-15]]:
            with self.assertRaises((ValueError, n.ET.ParseError)):
                self.rows(self.pin(data))
        source = self.pin(document([number()]))
        with (self.root / source['path']).open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaises(ValueError):
            n.shared.verify_pin(source, self.root)

    def test_multiple_open_reference_versions_fail_instead_of_picking_one(self):
        source = self.pin(document([space(), space()]), 'public_spaces')
        fake = {'snapshot_date': SNAPSHOT, 'sources': [source]}
        with self.assertRaisesRegex(ValueError, 'Multiple open reference'):
            n.reference_index(fake, self.root)

    def test_ignored_ranges_and_changed_container_versions_fail(self):
        container = {'url': 'https://service.pdok.nl/kadaster/bag/atom/downloads/lvbag-extract-nl.zip',
                     'bytes': 100, 'etag': 'version-one'}
        class Response(io.BytesIO):
            status = 200
            headers = {'Content-Length': '10', 'Content-Range': 'bytes 0-9/100', 'ETag': 'version-one'}
            def geturl(self): return container['url']
        with patch.object(n, 'urlopen', return_value=Response(b'0123456789')):
            with self.assertRaisesRegex(ValueError, 'version changed'):
                n.fetch_range(container, 0, 10)
        response = Response(b'0123456789');response.status = 206;response.headers = dict(response.headers, ETag='version-two')
        with patch.object(n, 'urlopen', return_value=response):
            with self.assertRaises(ValueError): n.fetch_range(container, 0, 10)
        with self.assertRaises(ValueError): n.fetch_range(container, 95, 10)

    def test_range_member_reconstruction_requires_crc_size_and_sha(self):
        payload = b'pinned original nested ZIP bytes' * 20
        compressor = zlib.compressobj(wbits=-15)
        compressed = compressor.compress(payload) + compressor.flush()
        filename = b'NUM.zip'
        header = struct.pack('<4s5H3I2H', b'PK\x03\x04', 20, 0, 8, 0, 0,
                             zlib.crc32(payload), len(compressed), len(payload), len(filename), 0)
        blob = header + filename + compressed
        pin = {'container_member': filename.decode(), 'offset': 0, 'method': 8,
               'compressed_bytes': len(compressed), 'bytes': len(payload),
               'crc32': f'{zlib.crc32(payload):08x}', 'sha256': n.hashlib.sha256(payload).hexdigest()}
        def fetch(container, start, length): return io.BytesIO(blob[start:start+length])
        with patch.object(n, 'fetch_range', side_effect=fetch):
            n.download_member({}, pin, self.root/'source.zip')
            self.assertEqual((self.root/'source.zip').read_bytes(), payload)
            changed = dict(pin, sha256='0'*64)
            with self.assertRaises(ValueError): n.download_member({}, changed, self.root/'bad.zip')
        self.assertFalse((self.root/'bad.zip').exists())
        self.assertFalse((self.root/'bad.zip.partial').exists())
        raced=self.root/'raced.zip.partial'
        def fetch_race(container,start,length):
            if start==30+len(filename): raced.write_bytes(b'another download owns this')
            return io.BytesIO(blob[start:start+length])
        with patch.object(n,'fetch_range',side_effect=fetch_race):
            with self.assertRaises(FileExistsError): n.download_member({},pin,self.root/'raced.zip')
        self.assertEqual(raced.read_bytes(),b'another download owns this')

    def test_prior_incomplete_downloads_are_preserved_before_network_access(self):
        partial=self.root/'source.zip.partial';partial.write_bytes(b'previous incomplete bytes')
        with patch.object(n,'fetch_range') as network:
            with self.assertRaisesRegex(ValueError,'explicit review'):
                n.download_member({}, {}, self.root/'source.zip')
            network.assert_not_called()
        self.assertEqual(partial.read_bytes(),b'previous incomplete bytes')
        pin={'id':'NL-file','country':'NL','path':'CBS.xlsx','requested_url':'https://www.cbs.nl/source',
             'bytes':1,'sha256':'0'*64}
        cbs_partial=self.root/'CBS.xlsx.partial';cbs_partial.write_bytes(b'keep this too')
        with patch.object(n,'urlopen') as network:
            with self.assertRaisesRegex(ValueError,'explicit review'):
                n.acquire({'sources':[pin]},self.root)
            network.assert_not_called()
        self.assertEqual(cbs_partial.read_bytes(),b'keep this too')

    def test_search_keeps_exact_numbers_pagination_and_snapshot_labelled_joins(self):
        source = self.pin(document([number(), number().replace('0001200000000001', '0001200000000002')]))
        manifest = {'snapshot_date': SNAPSHOT, 'sources': [source]}
        refs = {'public_spaces': {'0001300000000001': {'street_names': {'nl': 'Huidige naam'}, 'locality_id': '0001'}},
                'localities': {'0001': {'source_id': '0001', 'name': 'Plaats'}},
                'municipality_locality_links': {'0001': {'municipality_id': '0003'}},
                'municipalities': {'0003': {'source_id': '0003', 'name': 'Gemeente', 'province_id': 'PV20'}}}
        with patch.object(n, 'reference_index', return_value=(refs, {})):
            result = n.search(manifest, self.root, number='007', limit=1, current_only=True)
            self.assertTrue(result['has_more'])
            self.assertEqual(result['next_offset'], 1)
            self.assertEqual(result['results'][0]['reference_at_snapshot']['date'], SNAPSHOT)
            self.assertFalse(result['results'][0]['reference_at_snapshot']['gwr_link_is_authentic_bag_attribute'])
            second = n.search(manifest, self.root, number='007', limit=1, offset=1)
            self.assertEqual(second['results'][0]['source_id'], '0001200000000002')
            self.assertFalse(n.search(manifest, self.root, number='7')['results'])
            self.assertFalse(n.search(manifest, self.root, postcode='1234 AB')['results'])

    def test_manifest_and_accepted_audit_tampering_fail(self):
        published = json.loads(n.DEFAULT_MANIFEST.read_text())
        for changed in (dict(published, country='BE'), dict(published, national_completeness_verified=True),
                        dict(published, deliverability_in_scope=True), dict(published, sources=published['sources'][:-1])):
            path = self.root/'manifest.json';path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError): n.load_manifest(path)
        accepted = {'implementation_sha256': n.shared.sha256(n.__file__),
                    'shared_helpers_sha256': n.shared.sha256(n.shared.__file__),
                    'manifest_sha256': n.hashlib.sha256(n.shared.canonical(published).encode()).hexdigest(),
                    'source_reports': [{'counts': {'address': 10}}]}
        changed = copy.deepcopy(accepted);changed['source_reports'][0]['counts']['address'] = 11
        with patch.object(n, 'audit', return_value=accepted):
            self.assertEqual(n.replay(published, self.root, accepted)['source_row_replay'], 'PASS')
            with self.assertRaisesRegex(ValueError, 'replay differs'): n.replay(published, self.root, changed)
        changed = dict(accepted, implementation_sha256='0'*64)
        with self.assertRaisesRegex(ValueError, 'implementation'): n.replay(published, self.root, changed)

    def test_cbs_source_codes_and_province_parent_are_not_coerced(self):
        headers = ['Gemeentecode', 'GemeentecodeGM', 'Gemeentenaam', 'Provinciecode', 'ProvinciecodePV', 'Provincienaam']
        values = ['0003', 'GM0003', 'Naam met IJ', '20', 'PV20', 'Groningen']
        strings = headers + values
        ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        rel_ns = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
        def workbook(duplicate=False):
            path = self.root/'CBS.xlsx'
            rows = '<row r="1">' + ''.join(f'<c r="{c}1" t="s"><v>{i}</v></c>' for i,c in enumerate('ABCDEF')) + '</row>'
            for index in range(2,4 if duplicate else 3):
                rows += f'<row r="{index}">' + ''.join(f'<c r="{c}{index}" t="s"><v>{i+6}</v></c>' for i,c in enumerate('ABCDEF')) + '</row>'
            with zipfile.ZipFile(path,'w') as archive:
                archive.writestr('xl/sharedStrings.xml', f'<sst xmlns="{ns}">' + ''.join('<si><t>'+escape(s)+'</t></si>' for s in strings)+'</sst>')
                archive.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="{rel_ns}"><sheets><sheet name="Gemeenten_alfabetisch" r:id="rId1"/></sheets></workbook>')
                archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="rId1" Target="worksheets/sheet2.xml"/></Relationships>')
                archive.writestr('xl/worksheets/sheet2.xml', f'<worksheet xmlns="{ns}"><sheetData>{rows}</sheetData></worksheet>')
            return path
        source = {'id':'NL-CBS-fixture','country':'NL','sha256':'a'*64}
        row = list(n.cbs_records(workbook(),source))[0]
        self.assertEqual((row['source_id'],row['province_id']),('0003','PV20'))
        self.assertEqual(row['raw']['Gemeentecode'],'0003')
        with self.assertRaisesRegex(ValueError,'duplicate CBS'): list(n.cbs_records(workbook(True),source))

    def test_regional_cli_routes_nl_and_lists_both_source_sets(self):
        with patch.object(sys,'argv',['westerneurope.py','search','--country','NL']), patch.object(n,'main') as run:
            adapter.main();run.assert_called_once()
        output=self.root/'inventory.json'
        with patch.object(sys,'argv',['westerneurope.py','inventory','--output='+str(output)]): adapter.main()
        value=json.loads(output.read_text())
        self.assertEqual(len(value['sources']),116)
        self.assertEqual(len([s for s in value['sources'] if s['country']=='NL']),9)
        self.assertFalse(value['national_completeness_verified'])
        with patch.object(sys,'argv',['westerneurope.py','inventory','--country','AT','--output',str(output)]): adapter.main()
        self.assertEqual({s['country'] for s in json.loads(output.read_text())['sources']},{'AT'})

    def test_regional_audit_does_not_silently_omit_nl(self):
        with patch.object(sys,'argv',['westerneurope.py','audit']), patch('sys.stderr',new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as raised: adapter.main()
            self.assertEqual(raised.exception.code,2)


if __name__ == '__main__':
    unittest.main()
