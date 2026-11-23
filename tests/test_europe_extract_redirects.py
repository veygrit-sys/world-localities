"""Replay approved provider layouts through both public download functions."""
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import crown_four_localities as crown, europe_microstates as micro


class Response(io.BytesIO):
    status = 200

    def __init__(self, url):
        super().__init__(b"fixture bytes for download path tests")
        self.url = url

    def geturl(self):
        return self.url


class ExtractRedirects(unittest.TestCase):
    def test_only_paths_for_the_selected_region_are_accepted(self):
        for module, selected, slug in [(micro, "AD", "andorra"), (crown, "isle-of-man", "isle-of-man")]:
            root = "https://download.geofabrik.de/europe/"
            for suffix, accepted in [(f"{slug}-latest.osm.pbf", True), (f"{slug}-261122.osm.pbf", True),
                                     (f"{slug}/{slug}-261122.osm.pbf", True),
                                     (f"other/{slug}-261122.osm.pbf", False),
                                     (f"{slug}/other-261122.osm.pbf", False),
                                     (f"{slug}/{slug}-latest.osm.pbf?next=x", False)]:
                url = root + suffix
                with self.subTest(module=module.__name__, suffix=suffix), TemporaryDirectory() as tmp, \
                        patch.object(module, "urlopen", return_value=Response(url)):
                    if accepted:
                        self.assertEqual(module.download(selected, Path(tmp))["resolved_url"], url)
                    else:
                        with self.assertRaises(ValueError):
                            module.download(selected, Path(tmp))
                        self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_unrelated_hosts_credentials_and_ports_are_rejected(self):
        for module, selected, slug in [(micro, "AD", "andorra"), (crown, "guernsey-jersey", "guernsey-jersey")]:
            for host in ["download.geofabrik.de.evil.example", "user@download.geofabrik.de",
                         "download.geofabrik.de:8443"]:
                with self.subTest(module=module.__name__, host=host), TemporaryDirectory() as tmp, \
                        patch.object(module, "urlopen", return_value=Response(
                            f"https://{host}/europe/{slug}/{slug}-261122.osm.pbf")):
                    with self.assertRaises(ValueError):
                        module.download(selected, Path(tmp))
                    self.assertEqual(list(Path(tmp).iterdir()), [])
