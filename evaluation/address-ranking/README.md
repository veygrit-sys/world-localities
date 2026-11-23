# Offline candidate ranking

A separate, small pairwise logistic model ranks existing candidates in each of
three reference profiles: Japan Post town names, French La Poste communes, and
Washington, DC MAR street names. No third-party service, API key, customer
address, click log, or inference dependency is required. A score only compares
suggestions within one bounded pool; it cannot certify an address or its
deliverability. The picker keeps the upstream order for other sources,
countries, or kinds (including house numbers), and for untyped input.

Run from the repository root with the pinned postal snapshots:

```sh
python scripts/train_address_ranker.py --check
python scripts/train_address_ranker.py --output /tmp/address-ranker
python -m unittest discover -s tests -p test_address_ranker.py
```

The first command regenerates and checks both committed JSON files without
replacing them. It builds a temporary SQLite index containing **all** options
for the held-out postcodes. To reuse a complete index built from the same
snapshots, add `--index /path/to/index.sqlite`. The second writes new coefficients and a report to a separate folder.
The trainer reads reference labels through the picker's own parsers, never
retains premises or house numbers, and emits only coefficients and aggregate
counts. Training uses true pairs of published sibling names under the same
postcode and parent, with a synthetic typed prefix, a missing interior
character, a single word, or a Japanese suffix. Where several names fit an
ambiguous input, the originally selected name remains the target even though
more than one suggestion may be reasonable. A capped sample of at most 20
sibling names per group limits runtime and does not represent production
frequencies. Twelve numeric features describe textual agreement: prefixes,
character overlap, token and numeric agreement, among others.

Postcodes and normalized candidate names are independently hash-partitioned
before sampling; no label or country/postcode pair occurs on both sides. The
trainer checks this for **all candidates**, including negatives. The report
compares the learned ranker to a lexical baseline (exact name, name prefix, word
prefix, then provider order) on the retained candidate pools. MRR is mean
reciprocal rank. The separate `prefix_retrieval_and_ranking` figures apply the
actual picker prefix matcher to those same bounded sample pools and include
queries whose correct target was filtered out; the comparator here is the
picker's default ordering. These bounded-pool comparisons are not full-index recall, validation accuracy,
address-entry acceptance rates, or carrier acceptance rates. Synthetic variants
share a generation process between splits; independent user evaluation is
needed before setting service targets.

Results on the pinned inputs (top-1 includes ambiguous cases):

| Held-out reference | Typed queries | Known pool: lexical / learned | With picker prefix filter: source order / learned | Target survived filter |
| --- | ---: | ---: | ---: | ---: |
| France, commune | 608 | 66.45% / 98.36% | 56.58% / 56.91% | 356 / 608 |
| Japan, town | 577 | 34.14% / 77.64% | 19.58% / 19.76% | 230 / 577 |
| Washington, DC, street | 231 | 54.11% / 84.85% | 51.08% / 51.52% | 154 / 231 |

For the actual first-page experience, `full_picker_first_page` exercises the
public suggestion entry point and SQLite backend. It keeps all siblings for
each held-out postcode/parent (including natural distractors whose names were
seen in another postcode during training), requests a page of 20, and includes
every held-out typed query in the denominator. Held-out target names themselves
are still unseen. When no prefix matches, only a small source-qualified pool
can offer a spelling suggestion. For those pools, a single edit or adjacent
transposition is allowed on a whole name (at least three Japanese or four Latin
letters) or on a word-starting prefix (at least five letters). Numeric
characters, including CJK numeral ideographs, punctuation and mixed scripts
are excluded. A spelling suggestion requires user confirmation.

| Scope | Queries | Prefix only, correct first | Including spelling, correct first | Spelling first correct / returned |
| --- | ---: | ---: | ---: | ---: |
| FR | 608 | 337/608 (55.4%) | 584/608 (96.1%) | 247/247 |
| JP | 577 | 93/577 (16.1%) | 214/577 (37.1%) | 121/131 |
| US | 231 | 103/231 (44.6%) | 137/231 (59.3%) | 34/34 |

The target was absent from the page in 1 of 412 spelling responses. The
picker offered a spelling suggestion in 0 of 697 zero-prefix cross-postcode
controls in this sample.

The additional cross-postcode controls use complete names from a different
held-out postcode and exclude valid prefix matches in the queried scope.
They illustrate one type of irrelevant input, without estimating the
real-world false-positive rate. Many other incomplete or valid misspelled
inputs still produce no suggestion; they remain eligible for manual entry.

Sources: Japan Post, ordinary postal-code release of 2026-10-30
(`postal/sources/japanpost/20261030/utf_ken_all.zip`); La Poste – Service
National de l’Adresse, Base officielle des codes postaux, 2026-11-17, Licence
Ouverte 2.0 (`localities/open_reference/postal_eu/source.json`); District of
Columbia OCTO, Master Address Repository, snapshot retrieved 2026-11-21,
CC BY 4.0 (`localities/open_reference/us/citywide/citywide.json`). Refer to
the source manifests for attribution, source pins and upstream links. The DC
model does not establish performance elsewhere in the US.
