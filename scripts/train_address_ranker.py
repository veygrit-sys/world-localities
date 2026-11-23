#!/usr/bin/env python3
"""Rebuild the small country-specific address suggestion rankers without network or ML dependencies."""
from __future__ import annotations

import argparse
from contextlib import closing
from unittest.mock import patch
import sqlite3
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from addressing.address_ranker import FEATURES, MODEL_VERSION, features, fold
from localities.postal_picker import (PostalPicker, _digest, _matches_prefix, _option_id, _payload,
                                     _postcode, _query_key, _records, _write)
from localities.postal_picker_sources import iter_extra_records

COUNTRIES = {"FR": "area", "JP": "town", "US": "street"}
CAP = 20
OUTPUT = ROOT / "evaluation/address-ranking"


def stable(value):
    return int.from_bytes(sha256(value.encode()).digest()[:8], "big")


def split(key):
    return "test" if stable(key) % 5 < 2 else "train"


def groups():
    # Use the actual picker parsers and candidate levels, keeping no addresses,
    # premises, organizations, house numbers, user queries or identifiers.
    rows = defaultdict(set)
    for c, pc, steps, _ in iter_extra_records(set(COUNTRIES)):
        for i, (kind, place) in enumerate(steps):
            if kind != COUNTRIES[c] or not (2 <= len(place) <= 100):
                continue
            key = fold(place)
            if len(key) >= 2:
                rows[c, pc, steps[:i]].add(place)
            break
    return rows


@dataclass(frozen=True)
class Example:
    country: str
    pc: str
    parent: tuple
    target: str
    query: str
    variant: str
    pool: tuple[str, ...]


def variants(target, c):
    flat = target.replace(" ", "")
    if len(flat) < 2:
        return
    # Fixed conventions independent of model or score; keep collisions with
    # other candidates (including ambiguous prefixes) in the metrics.
    yield "prefix", target[:max(1, len(target)//2)].rstrip()
    if len(flat) >= 4:
        letters = [i for i, x in enumerate(target) if x != " " and 0 < i < len(target)-1]
        if letters:
            i = letters[stable(c + target) % len(letters)]
            yield "omission", target[:i] + target[i+1:]
    if c in {"FR", "US"} and " " in target:
        # Any word may be the one the user remembers.
        words = target.split()
        yield "one_word", words[stable(target + c) % len(words)]
    elif c == "JP" and len(flat) >= 3:
        yield "suffix", target[-max(2, len(target)//2):]


def dataset():
    rows = groups()
    partitions = {stage: defaultdict(list) for stage in ("train", "test")}
    metadata = {s: {} for s in partitions}
    for stage in partitions:
        for c in sorted(COUNTRIES):
            eligible = []
            for (country, pc, parent), labels in rows.items():
                if country != c or split(f"postcode:{c}:{pc}") != stage:
                    continue
                pool = sorted(x for x in labels if split("label:" + fold(x)) == stage)
                if len(pool) >= 2:
                    scope = f"{c}:{pc}:{parent!r}"
                    eligible.append((stable(scope), scope, pc, parent, pool))
            pcs, names = set(), set()
            # Oversized groups are deterministically subsampled; provider order
            # remains lexical, as it is in the picker for these named levels.
            for _, scope, pc, parent, pool in sorted(eligible)[:96 if stage == "train" else 64]:
                if len(pool) > CAP:
                    pool = sorted(sorted(pool, key=lambda x: stable(scope+x))[:CAP])
                pcs.add(pc)
                names.update(pool)
                for target in sorted(pool, key=lambda x: stable(x+scope))[:8]:
                    for variant, q in variants(_query_key(target), c):
                        partitions[stage][c].append(Example(c, pc, parent, target, q, variant, tuple(pool)))
            if not partitions[stage][c]:
                raise RuntimeError(f"no cases for {stage}/{c}")
            metadata[stage][c] = {"postcodes": len(pcs), "distinct_candidate_labels": len(names),
                                  "queries": len(partitions[stage][c]), "eligible_groups": len(eligible)}
    # Check all candidate identities across all three countries, not just positives.
    train, test = (sum(partitions[s].values(), []) for s in ("train", "test"))
    assert not ({fold(x) for e in train for x in e.pool} & {fold(x) for e in test for x in e.pool})
    assert not ({(e.country, e.pc) for e in train} & {(e.country, e.pc) for e in test})
    return partitions, metadata


def fit(examples):
    diffs = []
    for e in examples:
        q = fold(e.query)
        target = features(q, fold(e.target))
        for other in e.pool:
            if other != e.target:
                diffs.append(tuple(a-b for a, b in zip(target, features(q, fold(other)))))
    # Pairwise logistic loss, L2 penalty, deterministic mini-batch SGD. No
    # intercept: a shared intercept cancels in the score difference.
    weights = [0.] * len(FEATURES)
    rng = random.Random(41)
    for epoch in range(18):
        rng.shuffle(diffs)
        rate = 0.38 / math.sqrt(1 + epoch)
        for i in range(0, len(diffs), 48):
            batch = diffs[i:i+48]
            gradient = [0.] * len(weights)
            for diff in batch:
                dot = sum(a*b for a, b in zip(weights, diff))
                error = 1 / (1 + math.exp(min(50, dot)))
                for k, d in enumerate(diff):
                    gradient[k] += error*d
            for k in range(len(weights)):
                weights[k] += rate * (gradient[k]/len(batch) - 0.008*weights[k])
    return [round(x, 9) for x in weights], len(diffs)


def metrics(examples, weights):
    # A prefix baseline gives preference to exact labels, full-label prefixes,
    # and then word prefixes; ties preserve the picker's lexical order.
    totals = defaultdict(lambda: [0, 0, 0., 0, 0.])
    picker = defaultdict(lambda: [0, 0, 0, 0])
    for e in examples:
        q = fold(e.query)
        def lexical(s):
            s = fold(s)
            return (s == q, s.startswith(q), any(w.startswith(q) for w in s.split()))
        base = sorted(e.pool, key=lexical, reverse=True).index(e.target) + 1
        def score(s):
            return sum(v*w for v, w in zip(features(q, fold(s)), weights))
        fitted = sorted(e.pool, key=score, reverse=True).index(e.target) + 1
        retrieved = [s for s in e.pool if _matches_prefix(s, _query_key(e.query))]
        for key in ("all", e.variant):
            cell = picker[key]
            cell[0] += 1
            cell[1] += e.target in retrieved
            cell[2] += bool(retrieved and retrieved[0] == e.target)
            cell[3] += bool(retrieved and max(retrieved, key=score) == e.target)
        for key in ("all", e.variant):
            cell = totals[key]
            cell[0] += 1
            cell[1] += base == 1
            cell[2] += 1/base
            cell[3] += fitted == 1
            cell[4] += 1/fitted
    offline = {k: {"queries": n, "baseline_top1": round(b/n, 4), "model_top1": round(m/n, 4),
                "baseline_mrr": round(br/n, 4), "model_mrr": round(mr/n, 4)}
            for k, (n,b,br,m,mr) in sorted(totals.items())}
    prefix = {k: {"queries": n, "target_recalled": r, "ordered_top1": round(b/n, 4),
                  "model_top1": round(m/n, 4)} for k,(n,r,b,m) in sorted(picker.items())}
    return offline, prefix


def selected_path(country, pc, parent):
    digest, tokens = b"", []
    code = _postcode(country, pc)
    for kind, value in parent:
        tokens.append(_option_id(country, code, digest, kind, value))
        digest = _digest(country, code, digest, _payload(kind, value))
    return tokens


def full_picker_metrics(cases, country_weights, existing_index):
    from addressing.safe_suggest import suggest
    chosen = {(e.country, _postcode(e.country, e.pc)) for examples in cases.values() for e in examples}
    result = {}
    # Exercise the public picker and scoring code with the not-yet-published
    # in-memory weights. No model or test-only switch is written to the service.
    with tempfile.TemporaryDirectory() as temp, patch("addressing.address_ranker._weights", return_value=country_weights):
        if existing_index is None:
            index = Path(temp) / "evaluation.sqlite"
            # Restrict the generated index by held-out postcode ONLY; retain
            # all source candidates, mixed levels, siblings and metadata.
            with closing(sqlite3.connect(index)) as db:
                _write(db, (r for r in _records(set(COUNTRIES)) if
                            (r[0], _postcode(r[0], r[1])) in chosen))
        else:
            index = existing_index
        picker = PostalPicker(index)
        for c, examples in sorted(cases.items()):
            counts = defaultdict(lambda: defaultdict(int))
            paths = {(e.pc, e.parent): selected_path(c, e.pc, e.parent) for e in examples}
            for e in examples:
                answer = suggest(picker, c, e.pc, path=paths[e.pc, e.parent], query=e.query, limit=20)
                options = answer["options"]
                hit = any(o["label"] == e.target for o in options)
                first = bool(options and options[0]["label"] == e.target)
                rescue = answer["match_mode"] == "similar_spelling"
                for kind in ("all", e.variant):
                    cells = counts[kind]
                    cells["queries"] += 1
                    cells["prefix_top1"] += first and not rescue
                    cells["prefix_plus_spelling_top1"] += first
                    cells["correct_on_page"] += hit
                    cells["spelling_returned"] += rescue
                    cells["spelling_top1_correct"] += rescue and first
                    cells["spelling_target_absent_from_page"] += rescue and not hit
            # Queries are complete published names from another held-out
            # postcode. Exclude known prefixes at the queried scope, then
            # count false suggestions on these zero-prefix controls. They do
            # not represent user prevalence or equivalence reviewed by humans.
            controls = defaultdict(int)
            names = sorted({(e.pc, e.target) for e in examples})
            for (pc, parent), path in paths.items():
                others = sorted({target for code, target in names if pc != code},
                                key=lambda target: (stable(pc + repr(parent) + target), target))
                for q in others[:5]:
                    answer = suggest(picker, c, pc, path=path, query=q, limit=20)
                    if answer["match_mode"] == "prefix":
                        controls["excluded_prefix"] += 1
                        continue
                    controls["zero_prefix_queries"] += 1
                    controls["spelling_returned"] += bool(answer["options"])
            result[c] = {"labeled": {k: dict(v) for k,v in sorted(counts.items())},
                         "other_postcode_controls": dict(controls)}
    return result


def compute(existing_index=None):
    parts, splits = dataset()
    model = {"version": MODEL_VERSION, "features": list(FEATURES), "country_weights": {}}
    report = {"version": MODEL_VERSION, "metrics_scope": "offline ranking within a known candidate pool",
              "maximum_pool_size": CAP, "split": splits, "training_pairs": {}, "held_out": {}, "prefix_retrieval_and_ranking": {}}
    for c in sorted(COUNTRIES):
        weights, pairs = fit(parts["train"][c])
        model["country_weights"][c] = weights
        report["training_pairs"][c] = pairs
        report["held_out"][c], report["prefix_retrieval_and_ranking"][c] = metrics(parts["test"][c], weights)
    report["full_picker_first_page"] = full_picker_metrics(parts["test"], model["country_weights"], existing_index)
    return {"model.json": model, "report.json": report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if existing results cannot be reproduced")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--index", type=Path, help="existing same-snapshot picker index for JP, FR and US")
    args = parser.parse_args()
    for name, obj in compute(args.index).items():
        contents = json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        path = args.output / name
        if args.check:
            if contents != path.read_text(encoding="utf8"):
                parser.exit(1, f"stale result: {name}\n")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf8")
        print(name)


if __name__ == "__main__":
    main()
