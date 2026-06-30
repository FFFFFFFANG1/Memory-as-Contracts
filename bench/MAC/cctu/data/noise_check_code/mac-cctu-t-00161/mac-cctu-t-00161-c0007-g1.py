def evaluate(trace):
    import re
    allowed = {'green_belt_identifier','biologist_catalog_search'}
    calls = trace.get('tool_calls') or []
    bad = [c.get('name') for c in calls if c.get('name') not in allowed]
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    lines = [l for l in final.splitlines() if l.strip()]
    bullet_re = re.compile(r'^\s*([-*+\u2022]|\d+[.)])\s+')
    bullet_lines = [l for l in lines if bullet_re.match(l)]
    non_bullet = [l for l in lines if not bullet_re.match(l) and not re.match(r'^\s*#', l)]
    has_bullets = len(bullet_lines) >= 1
    narrative = len(non_bullet) > 0
    if bad:
        return {'observed_followed': False,'confidence':'high','reason':f'disallowed tools used: {bad}','evidence_refs':[]}
    if not has_bullets:
        return {'observed_followed': False,'confidence':'high','reason':'no bulleted shortlist present','evidence_refs':[]}
    if narrative:
        return {'observed_followed': False,'confidence':'medium','reason':f'non-bullet narrative lines present: {non_bullet[:2]}','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':'only allowed tools used; bulleted shortlist only','evidence_refs':[]}
