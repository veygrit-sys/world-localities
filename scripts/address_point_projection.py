"""Write deterministic, hash-pinned address-point shards for the offline postal picker."""

import csv
import gzip
import hashlib
import io
import json

FIELDS = ("postcode", "locality", "road", "number", "municipality", "record_id")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_projection(records, source, counts, target, rows_per_shard=20000):
    items = sorted(records)
    if not items:
        raise ValueError("empty projection")
    target.mkdir(parents=True, exist_ok=False)
    shards = []
    combined = hashlib.sha256()
    for offset in range(0, len(items), rows_per_shard):
        batch = items[offset:offset + rows_per_shard]
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(FIELDS)
        writer.writerows(batch)
        raw = buffer.getvalue().encode()
        combined.update(raw)
        out = io.BytesIO()
        with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as zipped:
            zipped.write(raw)
        filename = f"points-{len(shards) + 1:02}.csv.gz"
        (target / filename).write_bytes(out.getvalue())
        shards.append({"file": filename, "rows": len(batch), "sha256": sha(out.getvalue())})
    result = dict(source, counts=dict(counts, retained_ids=len(items),
                                      postcodes=len({r[0] for r in items})),
                  projection_sha256=combined.hexdigest(), shards=shards)
    (target / "source.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
