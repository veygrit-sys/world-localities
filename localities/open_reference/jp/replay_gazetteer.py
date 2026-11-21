"""Reproduce the Japanese gazetteer name projection from the pinned English PDF."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess


DIRECTORY = Path(__file__).resolve().parent
HEADER = ("source_row", "pdf_page", "grid", "classification", "kanji", "kana", "romanized")
CLASSES = {"Municipality", "Populated area"}
MISSING_KANJI = {199, 200, 1376, 2045, 3000, 3051}


def project(pages: str) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(HEADER)
    for page_no, page in enumerate(pages.split("\f"), 1):
        for line in page.splitlines():
            if not re.match(r"^\s*\d+\s+\d{4}\s", line):
                continue
            fields = re.split(r"\s{2,}", line.strip())
            if fields[-1] not in CLASSES:
                continue
            if len(fields) == 7 and int(fields[0]) in MISSING_KANJI:
                fields.insert(2, "")
            if len(fields) != 8:
                raise ValueError(f"unexpected Gazetteer columns on page {page_no}: {line}")
            ordinal, grid, kanji, kana, romanized, _, _, category = fields
            writer.writerow((ordinal, page_no, grid, category, kanji, kana, romanized))
    return output.getvalue().encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gazetteer_pdf", type=Path)
    parser.add_argument("errata_pdf", type=Path)
    args = parser.parse_args()
    manifest = json.loads((DIRECTORY / "source.json").read_text(encoding="utf-8"))
    for source_file, key in [(args.gazetteer_pdf, "gazetteer"), (args.errata_pdf, "errata")]:
        if hashlib.sha256(source_file.read_bytes()).hexdigest() != manifest[key]["sha256"]:
            parser.exit(1, f"unexpected SHA-256 for {key}\n")
    process = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(args.gazetteer_pdf.resolve()), "-"],
        check=True, stdout=subprocess.PIPE,
    )
    data = project(process.stdout.decode("utf-8"))
    if (hashlib.sha256(data).hexdigest() != manifest["projection"]["sha256"]
            or data != (DIRECTORY / "names.csv").read_bytes()):
        parser.exit(1, "extracted rows differ from the pinned projection\n")
    print(f"Verified {manifest['projection']['records']} gazetteer names.")


if __name__ == "__main__":
    main()
