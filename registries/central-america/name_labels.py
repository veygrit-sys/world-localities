"""Source-attested locale selection with explicit fallback status."""
from build import ROOT, read_csv

def select_label(entity_id, source_name, language, names):
    current=[r for r in names if r['entity_id']==entity_id and r['is_historic']!='1' and not r['valid_to']]
    requested=language.lower()
    for tag in dict.fromkeys([requested,requested.split('-')[0]]):
        matches=[r for r in current if r['language'].lower()==tag]
        if matches:
            matches.sort(key=lambda r:(r['is_preferred']!='1',r['is_colloquial']=='1',r['is_short']=='1',int(r['alternate_name_id'])))
            choice=matches[0]
            return {'display_name':choice['name'],'display_language':choice['language'],'name_status':'source_attested','name_evidence_id':choice['id'],'requested_language':language}
    return {'display_name':source_name,'display_language':'und','name_status':'source_name_fallback','name_evidence_id':'','requested_language':language}
