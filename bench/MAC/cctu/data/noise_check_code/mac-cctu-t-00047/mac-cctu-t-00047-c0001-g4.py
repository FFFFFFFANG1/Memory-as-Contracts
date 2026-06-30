def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = [l for l in text.splitlines() if l.strip().startswith('|')]
    if len(lines) < 2:
        return {'observed_followed': False,'confidence':'high','reason':'no markdown table found','evidence_refs':[]}
    has_sep = any(re.match(r'^\|\s*:?-{2,}', l) for l in lines)
    if not has_sep:
        return {'observed_followed': False,'confidence':'high','reason':'no markdown table separator row','evidence_refs':[]}
    header = lines[0].lower()
    need_mission = 'mission' in header
    need_crew = 'crew' in header
    need_fatal = ('fatal' in header) or ('death' in header) or ('casual' in header)
    if need_mission and need_crew and need_fatal:
        return {'observed_followed': True,'confidence':'high','reason':'table contains required columns','evidence_refs':[lines[0]]}
    missing = []
    if not need_mission: missing.append('mission name')
    if not need_crew: missing.append('crew size')
    if not need_fatal: missing.append('fatality count')
    return {'observed_followed': False,'confidence':'high','reason':'missing columns: '+','.join(missing),'evidence_refs':[lines[0]]}
