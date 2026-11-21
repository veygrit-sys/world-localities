"""Reproduce the overseas/Monaco entity crosswalk from the 2026 INSEE COG."""

import csv
import io

# These are COG parent codes, not postal prefixes. ISO alpha-2 for the
# named territories is documented in the UN Statistics Division M49 overview.
TERRITORIES = {
    "971": ("Guadeloupe", "GP"), "972": ("Martinique", "MQ"),
    "973": ("Guyane", "GF"), "974": ("La Réunion", "RE"), "976": ("Mayotte", "YT"),
    "975": ("Saint-Pierre-et-Miquelon", "PM"), "977": ("Saint-Barthélemy", "BL"),
    "978": ("Saint-Martin", "MF"), "986": ("Wallis-et-Futuna", "WF"),
    "987": ("Polynésie française", "PF"), "988": ("Nouvelle-Calédonie", "NC"),
}


def project(files: dict[str, bytes]) -> bytes:
    def rows(table):
        return csv.DictReader(io.StringIO(files[table].decode("utf-8-sig"), newline=""))

    parents = {row["DEP"]: row["LIBELLE"] for row in rows("departement")}
    entities = {}
    for row in rows("commune"):
        parent = row["DEP"]
        if row["TYPECOM"] == "COM" and parent in TERRITORIES:
            entities[row["COM"]] = parent, parents[parent]
    for row in rows("commune_comer"):
        if row["COMER"] in TERRITORIES:
            entities[row["COM_COMER"]] = row["COMER"], row["LIBELLE_COMER"]

    lines = io.StringIO(newline="")
    writer = csv.writer(lines, lineterminator="\n")
    writer.writerow(["insee_code", "parent_code", "parent_label", "country"])
    for code, (parent, label) in sorted(entities.items()):
        expected_name, iso = TERRITORIES[parent]
        if label != expected_name:
            raise ValueError(f"Unexpected COG parent {parent}: {label}")
        writer.writerow([code, parent, label, iso])
    monaco = [r for r in rows("pays_territoire") if r["COG"] == "99138"]
    if len(monaco) != 1 or (monaco[0]["CODEISO2"], monaco[0]["LIBCOG"]) != ("MC", "Monaco"):
        raise ValueError("Monaco country record differs in the INSEE COG")
    writer.writerow(["99138", "99138", "Monaco", "MC"])
    return lines.getvalue().encode("utf-8")
