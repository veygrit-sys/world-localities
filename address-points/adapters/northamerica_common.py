#!/usr/bin/env python3
"""North America source utilities; Python 3.10+, standard library only."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
import unicodedata
import zipfile

import os as _hierarchy_os
ROOT = Path(_hierarchy_os.environ.get('WORLD_LOCALITIES_ADDRESS_ROOT', str(Path(__file__).resolve().parents[1]))).resolve()
SOURCES = ROOT / 'sources/NORTHAMERICA'
GN_FIELDS = ['geonameid', 'name', 'asciiname', 'alternatenames', 'latitude', 'longitude',
             'feature_class', 'feature_code', 'country_code', 'cc2', 'admin1', 'admin2',
             'admin3', 'admin4', 'population', 'elevation', 'dem', 'timezone', 'modified_date']
NAME_FIELDS = ['alternate_name_id', 'geonameid', 'language', 'name', 'preferred',
               'short', 'colloquial', 'historic', 'from', 'to']
NON_NAME_TAGS = {'post', 'iata', 'icao', 'faac', 'link', 'wkdt', 'unlc', 'tcid'}
HISTORIC_FEATURES = {'PPLH', 'PPLCH', 'PPLQ', 'PPLW'}


def read_json(path):
    data = Path(path).read_bytes()
    if data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)
    return json.loads(data.decode('utf-8-sig'))

def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))

def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def lookup_key(value):
    """Lossy retrieval key only. Never an identity, transliteration or display name."""
    if not isinstance(value, str):
        raise ValueError('Names and address components must be strings')
    value = unicodedata.normalize('NFKD', value).casefold()
    return ' '.join(''.join(c for c in value if not unicodedata.combining(c)).split())

def zip_rows(path, cc):
    with Path(path).open('rb') as f:
        wrapped = f.read(2) == b'\x1f\x8b'
    source = io.BytesIO(gzip.decompress(Path(path).read_bytes())) if wrapped else path
    with zipfile.ZipFile(source) as z:
        name = cc + '.txt'
        if name not in z.namelist():
            raise ValueError(f'Missing {name} in {path}')
        with z.open(name) as raw:
            yield from csv.reader(io.TextIOWrapper(raw, encoding='utf-8', newline=''), delimiter='\t', quoting=csv.QUOTE_NONE)

def historical_or_time_bounded_name(raw):
    # Use the release date, not execution time, for reproducible snapshot filtering.
    if raw.get('historic') == '1' or raw.get('to'):
        return True
    start = raw.get('from')
    if not start:
        return False
    as_of = date.fromisoformat(read_json(ROOT / 'NORTH_AMERICA_RULES.json')['release_date'])
    if not re.fullmatch(r'[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?', start):
        return True
    bits = start.split('-')
    try:
        parsed = date(int(bits[0]), int(bits[1]) if len(bits)>1 else 1, int(bits[2]) if len(bits)>2 else 1)
    except ValueError:
        return True
    return parsed > as_of


def profiles():
    return read_json(ROOT/'NORTH_AMERICA_RULES.json')['profiles']


def country_code(value):
    if not isinstance(value,str) or value.upper() not in profiles():
        raise ValueError('Unsupported North America country or supplementary area')
    return value.upper()


def verify_sources():
    manifest=read_json(ROOT/'NORTH_AMERICA_SOURCES.json')
    if manifest.get('failures') or not manifest.get('sources'):
        raise ValueError('Source acquisition is incomplete')
    seen=set()
    for s in manifest['sources']:
        p=(SOURCES/s['path']).resolve()
        if s['id'] in seen or not p.is_relative_to(SOURCES.resolve()):
            raise ValueError('Duplicate source ID or unsafe source path')
        seen.add(s['id'])
        if not p.is_file() or p.stat().st_size!=s['bytes'] or file_hash(p)!=s['sha256']:
            raise ValueError('Source integrity mismatch: '+s['id'])
    if seen!=set(manifest['required_source_ids']):
        raise ValueError('Source inventory mismatch')
    return manifest


def decoded(path):
    b=Path(path).read_bytes()
    return gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b


def csv_rows(path,member=None,delimiter=',',encoding='utf-8-sig'):
    b=decoded(path)
    if member is not None:
        with zipfile.ZipFile(io.BytesIO(b)) as z:b=z.read(member)
    reader=csv.DictReader(io.StringIO(b.decode(encoding),newline=''),delimiter=delimiter)
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise ValueError('Malformed CSV record')
        yield row


def dbf_rows(path):
    """Preserve character and numeric fields as strings, including leading zeroes."""
    import struct
    with zipfile.ZipFile(io.BytesIO(decoded(path))) as z:
        members=[n for n in z.namelist() if n.lower().endswith('.dbf')]
        if len(members)!=1:raise ValueError('Expected one DBF member')
        b=z.read(members[0]);cpg=[n for n in z.namelist() if n.lower().endswith('.cpg')]
        encoding=z.read(cpg[0]).decode('ascii').strip() if cpg else 'cp1252'
        if encoding=='65001':encoding='utf-8'
    count,hlen,rlen=struct.unpack_from('<IHH',b,4)
    if len(b)<hlen+count*rlen:raise ValueError('Truncated DBF')
    fields=[]
    for i in range(32,hlen-1,32):
        f=b[i:i+32]
        if f[:1]==b'\r':break
        fields.append((f[:11].split(b'\0')[0].decode('ascii'),f[16]))
    if 1+sum(n for _,n in fields)!=rlen:raise ValueError('DBF width mismatch')
    for index in range(count):
        raw=b[hlen+index*rlen:hlen+(index+1)*rlen]
        if raw[:1]!=b' ':raise ValueError('Deleted or invalid DBF row needs review')
        row={};offset=1
        for name,width in fields:
            row[name]=raw[offset:offset+width].decode(encoding).strip();offset+=width
        yield row


def postcode_review(cc,value):
    cc=country_code(cc)
    out={'country':cc,'raw':value,'assignment_verified':False,'delivery_verified':False}
    if value is None or value=='':return {**out,'status':'missing'}
    if not isinstance(value,str):return {**out,'status':'invalid_input_type'}
    candidate=value.strip().upper()
    if not candidate.isascii():return {**out,'status':'review_required'}
    pattern=profiles()[cc]['postcode_pattern']
    return {**out,'status':'matches_syntax_only' if re.fullmatch(pattern,candidate) else 'review_required','display_candidate':candidate}
