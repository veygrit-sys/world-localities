"""Offline, source-constrained ranking of address picker options.

Scores only order existing suggestions; they are not match probabilities or
evidence of residential occupancy, an address-point match, or deliverability.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

MODEL_FILE = Path(__file__).resolve().parents[1] / "evaluation/address-ranking/model.json"
MAX_QUERY = 160
MAX_LABEL = 512
MAX_CANDIDATES = 512
MODEL_VERSION = "address-ranker-v1"
FEATURES = ("exact", "prefix", "infix", "common_prefix", "length_ratio", "bigram_dice",
            "sequence_ratio", "token_recall", "token_precision", "word_prefix", "number_recall",
            "reverse_substring")


def fold(value: str) -> str:
    """Search-only: preserve Japanese voicing marks; strip accents on Latin letters."""
    parts = []
    latin = False
    for c in unicodedata.normalize("NFKD", value.casefold()):
        if unicodedata.combining(c):
            if not latin:
                parts.append(c)
            continue
        latin = "LATIN" in unicodedata.name(c, "")
        parts.append(c if c.isalnum() else " ")
    return " ".join(unicodedata.normalize("NFC", "".join(parts)).split())


def _fuzzy_text(value):
    # Restrict BEFORE lossy search folding so digits, house/unit separators,
    # wildcards or other controls cannot disappear during normalization.
    if not isinstance(value, str) or len(value) > MAX_LABEL or not value.isprintable():
        return "", ""
    value = unicodedata.normalize("NFKC", value).strip()
    script = None
    preceding = None
    for ch in value:
        if ch.isnumeric():
            return "", ""
        if ch == " ":
            preceding = None
            continue
        name = unicodedata.name(ch, "")
        if unicodedata.combining(ch) and preceding:
            continue
        if "LATIN" in name and ch.isalpha():
            current = "latin"
        elif (ch.isalpha() and ("HIRAGANA" in name or "KATAKANA" in name or
                                "CJK UNIFIED IDEOGRAPH" in name or "CJK COMPATIBILITY IDEOGRAPH" in name)):
            current = "jp"
        else:
            return "", ""
        if script and current != script:
            return "", ""
        preceding = script = current
    return (fold(value), script) if script else ("", "")


def _one_edit(a, b):
    """One insertion, omission, substitution or adjacent transposition."""
    if abs(len(a)-len(b)) > 1 or a == b:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    if len(a) != len(b):
        return a[i:] == b[i+1:]
    if a[i+1:] == b[i+1:]:
        return True
    return (i+1 < len(a) and a[i] == b[i+1] and a[i+1] == b[i] and a[i+2:] == b[i+2:])


def fuzzy_matches(query: str, label: str) -> bool:
    """Conservative rescue for source-qualified names in small zero-prefix pools.

    Never apply to addresses, identifiers or numbers. The caller must enforce
    the source, candidate kind, bounded parent, postcode and empty-prefix
    requirements before using this predicate.
    """
    if not isinstance(query, str) or len(query) > MAX_QUERY:
        return False
    q, script = _fuzzy_text(query)
    s, other = _fuzzy_text(label)
    if not script or script != other:
        return False
    n = len(q.replace(" ", ""))
    if n < (3 if script == "jp" else 4):
        return False
    if q == s or _one_edit(q, s):
        return True
    # For longer typed strings one edit may occur inside a typed name prefix,
    # beginning at the start of a source word. Keep spaces significant.
    if n < 5:
        return False
    for start in (m.start() for m in re.finditer(r"(?<!\S)\S", s)):
        for size in (len(q)-1, len(q), len(q)+1):
            part = s[start:start+size]
            if len(part) == size and (q == part or _one_edit(q, part)):
                return True
    return False


def features(q: str, s: str) -> tuple[float, ...]:
    """q and s are already folded; all features are independent of candidate identity."""
    a, b = q.replace(" ", ""), s.replace(" ", "")
    if not a or not b:
        return (0.0,) * len(FEATURES)
    qwords, swords = q.split(), s.split()
    qt, st = set(qwords), set(swords)
    ag, bg = {a[i:i+2] for i in range(len(a)-1)}, {b[i:i+2] for i in range(len(b)-1)}
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    qn, sn = set(re.findall(r"\d+", q)), set(re.findall(r"\d+", s))
    return (float(a == b), float(b.startswith(a)), float(a in b), n/len(a),
            min(len(a), len(b))/max(len(a), len(b)), 2*len(ag & bg)/max(1, len(ag)+len(bg)),
            SequenceMatcher(None, a, b, autojunk=False).ratio(), len(qt & st)/len(qt),
            len(qt & st)/len(st), sum(any(t.startswith(w) for t in swords) for w in qwords)/len(qwords),
            len(qn & sn)/max(1, len(qn)), float(b in a))


@lru_cache(maxsize=1)
def _weights():
    with MODEL_FILE.open(encoding="utf8") as f:
        model = json.load(f)
    if (not isinstance(model, dict) or model.get("version") != MODEL_VERSION or
            model.get("features") != list(FEATURES)):
        raise ValueError("incompatible address ranker artifact")
    weights = model.get("country_weights")
    if (not isinstance(weights, dict) or set(weights) != set(_TRAINED_POOLS) or
            not all(isinstance(row, list) and len(row) == len(FEATURES) and
                    all(type(v) in (float, int) and abs(v) < 100 and math.isfinite(v) for v in row)
                    for row in weights.values())):
        raise ValueError("invalid address ranker coefficients")
    return weights


# These are the source profiles represented in the training and holdout.
_TRAINED_POOLS = {"FR": ("area", "fr-laposte-hexasmal"),
                  "JP": ("town", "japanpost-postal-20261030"),
                  "US": ("street", "us-dc-mar")}


def supports_country(country) -> bool:
    return isinstance(country, str) and country.upper() in _TRAINED_POOLS


def supports_pool(country, rows, *, source_key="source_id", allow_untyped=False, min_rows=2) -> bool:
    if not supports_country(country) or len(rows) < min_rows:
        return False
    kind, source = _TRAINED_POOLS[country.upper()]

    def has_source(row):
        references = row.get("supporting_sources")
        return (row.get(source_key) == source or
                isinstance(references, (list, tuple)) and source in references)
    return all(isinstance(row, Mapping) and (row.get("kind") == kind or allow_untyped and "kind" not in row)
               and has_source(row) for row in rows)


def _postcode(value, country):
    if not isinstance(value, str) or not value.isprintable() or len(value) > 64:
        return ""
    value = " ".join(unicodedata.normalize("NFKC", value).strip().upper().split())
    return value.replace("-", "") if country == "JP" and re.fullmatch(r"[0-9]{3}-[0-9]{4}", value) else value


def rank_candidates(query: str, candidates: Sequence[Mapping], *, country_code: str, postcode: str,
                    label_key: str = "label", source_key: str = "source_id",
                    country_key: str = "country_code", postcode_key: str = "postcode") -> list:
    """Return original rows in relevance order, limited to an exact source-scoped pool.

    Empty search text and countries without a trained model preserve provider
    order; whitespace and JP postcode display normalization never removes a
    postcode digit. Ties retain provider order. No query or score is persisted.
    """
    if not isinstance(query, str) or len(query) > MAX_QUERY:
        raise ValueError(f"query must be a string of at most {MAX_QUERY} characters")
    if len(candidates) > MAX_CANDIDATES:
        raise ValueError(f"candidate pool exceeds {MAX_CANDIDATES}")
    country = country_code.strip().upper() if isinstance(country_code, str) else ""
    pc = _postcode(postcode, country)
    if not re.fullmatch(r"[A-Z]{2}", country) or not pc:
        return []
    rows = []
    for row in candidates:
        if not isinstance(row, Mapping):
            continue
        cc, label, source = row.get(country_key), row.get(label_key), row.get(source_key)
        if (isinstance(cc, str) and cc.strip().upper() == country and
                _postcode(row.get(postcode_key), country) == pc and
                isinstance(source, str) and source.strip() and
                isinstance(label, str) and label.strip() and len(label) <= MAX_LABEL):
            rows.append(row)
    q = fold(query)
    if not q or len(rows) < 2 or not supports_country(country):
        return rows
    # The picker supplies kinds. Unknown, mixed, numeric or untested levels
    # retain provider order. Standalone callers can submit a generic named
    # pool without kinds when they explicitly choose a trained country model.
    if not supports_pool(country, rows, source_key=source_key, allow_untyped=all("kind" not in r for r in rows)):
        return rows
    weights = _weights().get(country)
    if weights is None:
        return rows
    return sorted(rows, key=lambda row: sum(w*v for w, v in zip(weights, features(q, fold(row[label_key])))),
                  reverse=True)
