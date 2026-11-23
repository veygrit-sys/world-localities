"""Review deferred sources and retain independent European acquisition results."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import lzma
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

INVENTORY = "docs/plans/source-recovery-20261124.json"
PRIORITIES = ("P0", "P1", "P2", "P3")
STATES = {"recovered", "retry_source", "permission_review", "extraction_review",
          "identity_review", "assignment_source_needed", "rejected_candidate"}


def load_inventory(root=ROOT):
    root = Path(root)
    doc = json.loads((root / INVENTORY).read_text(encoding="utf-8"))
    if doc.get("schema_version") != 1 or not isinstance(doc.get("entries"), list):
        raise ValueError("unsupported recovery inventory")
    seen, covered = set(), set()
    for entry in doc["entries"]:
        if entry["id"] in seen or entry["priority"] not in PRIORITIES or entry["status"] not in STATES:
            raise ValueError("invalid or duplicate recovery entry")
        seen.add(entry["id"])
        if not entry["country_codes"] or not entry["reason"] or not entry["next_action"]:
            raise ValueError("recovery entry lacks scope or decision")
        for ref in entry["previous_decisions"]:
            path, key, index = ref["path"], ref["key"], ref["index"]
            historical = json.loads((root / path).read_text(encoding="utf-8"))[key][index]
            if historical["country_code"] not in entry["country_codes"]:
                raise ValueError("historical country differs from recovery entry")
            covered.add((path, key, index))
        for path in entry.get("evidence_paths", []):
            if not (root / path).is_file():
                raise ValueError("missing recovery evidence: " + path)
    expected = set()
    for path, key in [("postal/stage3-review.json", "deferred"),
                      ("postal/stage4-review.json", "deferred_candidates")]:
        old = json.loads((root / path).read_text(encoding="utf-8"))[key]
        expected.update((path, key, index) for index in range(len(old)))
    if covered != expected:
        raise ValueError("deferred postal decisions are missing from recovery review")
    return doc


def select_entries(doc, *, priority=None, country=None, status=None):
    return [entry for entry in doc["entries"]
            if (priority is None or entry["priority"] == priority)
            and (country is None or country in entry["country_codes"])
            and (status is None or entry["status"] == status)]


def verify_saved_snapshots(root=ROOT):
    from scripts import crown_four_localities as crown, europe_microstates as micro
    root = Path(root)
    results = {}
    for collection, module in [("microstates", micro), ("crown", crown)]:
        report = json.loads((root / f"releases/source-recovery/20261124/{collection}-intake.json").read_text())
        raw = root / report["source_root"]
        for pin in report["source_pins"]:
            if collection == "microstates":
                module.check_receipt(pin, pin["country"], raw)
            else:
                module.checked_pin(pin, raw)
        snapshot = report["snapshot"]
        compressed = root / snapshot["path"]
        if (compressed.stat().st_size != snapshot["bytes"]
                or hashlib.sha256(compressed.read_bytes()).hexdigest() != snapshot["sha256"]):
            raise ValueError("compressed index differs from pinned snapshot")
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "index.sqlite"
            digest, size = hashlib.sha256(), 0
            with lzma.open(compressed, "rb") as source, database.open("xb") as target:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > snapshot["uncompressed_bytes"]:
                        raise ValueError("expanded index exceeds pinned size")
                    digest.update(chunk)
                    target.write(chunk)
            if size != snapshot["uncompressed_bytes"] or digest.hexdigest() != snapshot["uncompressed_sha256"]:
                raise ValueError("expanded index differs from pinned snapshot")
            verified = module.verify(database)
            if verified != report["verified_index"]:
                raise ValueError("saved source index report differs")
            results[collection] = verified
    return results


def download_europe(collection, directory, report_path):
    """Attempt every selected source; a failed download never counts as intake."""
    from scripts import crown_four_localities as crown, europe_microstates as micro
    if collection == "microstates":
        module, sources = micro, list(micro.CODES)
    elif collection == "crown":
        module, sources = crown, list(crown.EXTRACTS)
    else:
        raise ValueError("unknown European source collection")
    directory, report_path = Path(directory), Path(report_path)
    if not directory.is_dir() or report_path.exists() or report_path.is_symlink():
        raise ValueError("use an existing source directory and a new report path")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    results = []
    for source in sources:
        started = datetime.now(timezone.utc).isoformat()
        try:
            pin = module.download(source, directory)
        except (OSError, ValueError) as error:
            results.append({"source": source, "started_at": started,
                            "status": "failed", "error_type": type(error).__name__,
                            "error": str(error)})
        else:
            results.append({"source": source, "started_at": started,
                            "status": "downloaded", "pin": pin})
        # Persist progress even if a later source or the runner fails.
        report = {"schema_version": 1, "collection": collection,
                  "completed": len(results) == len(sources), "results": results,
                  "successful": sum(item["status"] == "downloaded" for item in results),
                  "failed": sum(item["status"] == "failed" for item in results),
                  "index_built": False, "national_completeness_verified": False,
                  "deliverability_verified": False}
        temporary = report_path.with_suffix(report_path.suffix + ".partial")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(report_path)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("list")
    review.add_argument("--priority", choices=PRIORITIES)
    review.add_argument("--country", type=str.upper)
    review.add_argument("--status", choices=sorted(STATES))
    sub.add_parser("verify")
    sub.add_parser("verify-snapshots")
    download = sub.add_parser("download-europe")
    download.add_argument("--collection", choices=("microstates", "crown"), required=True)
    download.add_argument("--directory", type=Path, required=True)
    download.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "verify-snapshots":
        print(json.dumps(verify_saved_snapshots(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "download-europe":
        result = download_europe(args.collection, args.directory, args.report)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["failed"] else 0
    doc = load_inventory()
    if args.command == "verify":
        result = {"status": "PASS", "entries": len(doc["entries"]),
                  "states": dict(Counter(entry["status"] for entry in doc["entries"]))}
    else:
        result = select_entries(doc, priority=args.priority, country=args.country, status=args.status)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
