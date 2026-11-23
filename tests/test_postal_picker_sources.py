"""Check selection paths against diverse rows in the official snapshots."""

from collections import Counter, defaultdict
import unittest

from localities.postal_picker_sources import iter_extra_records


class PostalPickerSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Exercise the normal source iterator once, retaining selected codes only.
        samples = {
            "JP": {"0391544", "0600042", "0640941", "1000000", "1006901", "1006990",
                   "3060433", "0608621", "0608703", "1008919", "4506201"},
            "FR": {"20167", "75007", "98000", "97400"},
            "RE": {"97400"}, "MC": {"98000"}, "PM": {"97500"}, "PF": {"98714"},
            "US": {"20001", "20002", "20017", "20032"},
            "MU": {"71501", "R6401", "A1101", "712547"},
        }
        cls.paths = defaultdict(set)
        cls.sources = defaultdict(set)
        cls.counts = Counter()
        for country, code, steps, source_id in iter_extra_records(samples):
            cls.counts[country] += 1
            cls.sources[country].add(source_id)
            if code in samples[country]:
                cls.paths[country, code].add(steps)

    def test_japan_many_towns_and_postal_scope(self):
        area = ("area", "青森県 三戸郡五戸町")
        self.assertEqual(self.paths["JP", "0391544"], {
            (area, ("town", "二階平")), (area, ("town", "二階平下タ")),
        })
        area = ("area", "北海道 札幌市中央区")
        self.assertEqual(self.paths["JP", "0640941"], {(area, ("town", "旭ケ丘"))})
        self.assertEqual(self.paths["JP", "0600042"], {
            (area, ("town", "大通西"), ("qualifier", "１〜１９丁目")),
        })
        self.assertEqual(self.paths["JP", "1000000"], {(("area", "東京都 千代田区"),)})
        self.assertEqual(self.paths["JP", "3060433"], {
            (("area", "茨城県 猿島郡境町"), ("qualifier", "境町の次に番地がくる場合")),
        })
        self.assertEqual(self.paths["JP", "1008919"], {(
            ("published_office", "外務省"), ("published_office_address", "東京都千代田区霞が関２丁目２－１"),
        )})
        self.assertTrue(all(steps[0][0] == "published_office" for steps in self.paths["JP", "0608621"]))
        self.assertFalse(self.paths["JP", "0608703"])  # A PO box cannot become a street address.

    def test_buildings_keep_exact_numbered_floor_and_conditional_floor(self):
        area = ("area", "東京都 千代田区")
        self.assertEqual(self.paths["JP", "1006901"], {
            (area, ("building", "丸の内丸の内パークビルディング（１階）")),
        })
        self.assertEqual(self.paths["JP", "1006990"], {
            (area, ("building", "丸の内丸の内パークビルディング"), ("qualifier", "地階・階層不明")),
        })
        self.assertEqual(self.paths["JP", "4506201"], {
            (("area", "愛知県 名古屋市中村区"), ("building", "名駅ミッドランドスクエア（高層棟）（１階）")),
        })

    def test_la_poste_keeps_commune_routing_and_line_five_in_territory(self):
        self.assertIn((("area", "AJACCIO"), ("town", "MEZZAVIA")), self.paths["FR", "20167"])
        self.assertIn((("area", "AFA"),), self.paths["FR", "20167"])
        self.assertNotIn((("area", "AFA"), ("town", "MEZZAVIA")), self.paths["FR", "20167"])
        self.assertEqual(self.paths["FR", "75007"], {(("area", "PARIS 07"), ("routing_name", "PARIS"))})
        self.assertEqual(self.paths["MC", "98000"], {(("area", "MONACO"),)})
        self.assertIn((("area", "ST DENIS"), ("town", "BELLE PIERRE")), self.paths["RE", "97400"])
        self.assertFalse(self.paths["FR", "97400"] | self.paths["FR", "98000"])
        self.assertIn((("area", "MIQUELON LANGLADE"), ("town", "LANGLADE"),
                       ("routing_name", "ST PIERRE ET MIQUELON")), self.paths["PM", "97500"])
        self.assertEqual(self.paths["PF", "98714"], {(("area", "PAPEETE"),)})

    def test_washington_dc_addresses_keep_number_suffix_and_street_boundaries(self):
        area = ("area", "Washington, DC")
        g_street = ("street", "G STREET NW")
        self.assertIn((area, g_street, ("house_number", "901")), self.paths["US", "20001"])
        self.assertNotIn((area, g_street, ("house_number", "903")), self.paths["US", "20001"])
        self.assertIn((area, ("street", "BUCHANAN STREET NE"), ("house_number", "610 1/2")),
                      self.paths["US", "20017"])
        self.assertIn((area, ("street", "CONSTITUTION AVENUE NE"), ("house_number", "645 REAR")),
                      self.paths["US", "20002"])
        for address in ("625 A CHESAPEAKE STREET SE", "800 H R DRIVE SE"):
            self.assertIn((area, ("address", address)), self.paths["US", "20032"])

    def test_mauritian_streets_and_postal_sections_remain_distinct(self):
        area = (("area", "Beau Bassin"), ("town", "BEAU BASSIN CENTRE 1"))
        self.assertIn(area + (("street", "Dessenes St"),), self.paths["MU", "71501"])
        self.assertIn(area + (("qualifier", "Meldrum _Southern Side"),), self.paths["MU", "71501"])
        self.assertFalse(self.paths["MU", "712547"])  # Flagged as anomalous in the source reader.
        self.assertEqual(self.paths["MU", "A1101"], {(("area", "Agalega"), ("town", "La Fourche"))})
        self.assertIn((("area", "Grand Montagne"), ("town", "Anse Ally_Fumier")), self.paths["MU", "R6401"])

    def test_source_manifest_and_country_scope(self):
        self.assertEqual(self.sources["US"], {"us-dc-mar"})
        self.assertEqual(self.sources["FR"], {"fr-laposte-hexasmal"})
        self.assertEqual(self.sources["JP"], {"japanpost-postal-20261030", "japanpost-business-20261030"})
        self.assertEqual(self.counts["US"], 141189)
        self.assertEqual(self.counts["FR"], 38716)
        self.assertEqual(self.counts["MU"], 4235)
        self.assertEqual(list(iter_extra_records([])), [])
        self.assertEqual(list(iter_extra_records(["CA", "TW"])), [])
        self.assertEqual(list(iter_extra_records("MC")), [
            ("MC", "98000", (("area", "MONACO"),), "fr-laposte-hexasmal"),
        ])
