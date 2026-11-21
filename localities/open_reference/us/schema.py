"""Stable columns and canonical object-ID fingerprint for DC MAR excerpts."""

from hashlib import sha256

FIELDS = ("MAR_ID", "OBJECTID", "ADDRESS", "CITY", "STATE", "ZIPCODE", "LATITUDE", "LONGITUDE")


def _id_set_hash(object_ids) -> str:
    return sha256("".join(f"{oid}\n" for oid in sorted(object_ids)).encode("ascii")).hexdigest()
