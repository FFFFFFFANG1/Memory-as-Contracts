def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = [l for l in text.splitlines() if l.strip()]
    bullet_re = re.compile(r'^\s*([\-\*\+•]|\d+[.)])\s+')
    bullets = [l for l in lines if bullet_re.match(l)]
    has_table = ('|' in text and re.search(r'\|.*\|', text) is not None) or re.search(r'^\s*\|', text, re.M) is not None or re.search(r'-{3,}\s*\|', text) is not None
    if has_table:
        return {'observed_followed': False,'confidence':'high','reason':'response contains a table','evidence_refs':[]}
    if not bullets:
        return {'observed_followed': False,'confidence':'high','reason':'no bulleted list found','evidence_refs':[]}
    non_bullet_content = [l for l in lines if not bullet_re.match(l)]
    if len(bullets) > 3:
        return {'observed_followed': False,'confidence':'high','reason':f'{len(bullets)} bullet lines exceed max 3','evidence_refs':[]}
    if len(non_bullet_content) > 0:
        # allow if they are clearly not content lines? Be strict-ish
        return {'observed_followed': False,'confidence':'medium','reason':'non-bullet content lines present','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':f'{len(bullets)} bullets, no tables','evidence_refs':[]}
