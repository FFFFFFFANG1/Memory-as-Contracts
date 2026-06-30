def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = [ln for ln in resp.splitlines() if ln.strip()]
    if not lines:
        return {'observed_followed': False,'confidence':'high','reason':'no content lines','evidence_refs':[]}
    bullet_re = re.compile(r'^\s*([-*•+]|\d+[.)])\s+')
    bullet_lines = [ln for ln in lines if bullet_re.match(ln)]
    non_bullet = [ln for ln in lines if not bullet_re.match(ln)]
    if len(bullet_lines) < 1:
        return {'observed_followed': False,'confidence':'high','reason':'response is not a bullet list','evidence_refs':[resp[:160]]}
    if non_bullet:
        # any non-bullet line (e.g., concluding marker, header, summary) violates
        return {'observed_followed': False,'confidence':'high','reason':'non-bullet line present (possible concluding marker): ' + non_bullet[-1][:120],'evidence_refs':non_bullet[:3]}
    return {'observed_followed': True,'confidence':'medium','reason':f'{len(bullet_lines)} bullets, no concluding marker line','evidence_refs':[]}
