def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    lines = [l for l in text.splitlines() if l.strip()]
    bullet_re = re.compile(r'^\s*(?:[-*+\u2022]|\d+[.)])\s+')
    bullets = [l for l in lines if bullet_re.match(l)]
    non_bullets = [l for l in lines if not bullet_re.match(l)]
    # allow an optional intro/heading line? Strictly: response should be bullets only.
    has_table_pipe = any('|' in l and l.count('|')>=2 for l in lines)
    has_table_sep = any(re.match(r'^\s*\|?\s*:?-{3,}', l) for l in lines)
    has_tab_table = any('\t' in l for l in lines)
    tabular = has_table_pipe or has_table_sep or has_tab_table
    if not bullets:
        return {'observed_followed': False,'confidence':'high','reason':'no bulleted list detected','evidence_refs':[]}
    if len(bullets) > 5:
        return {'observed_followed': False,'confidence':'high','reason':f'{len(bullets)} bullets exceeds 5','evidence_refs':[]}
    if tabular:
        return {'observed_followed': False,'confidence':'high','reason':'tabular layout detected','evidence_refs':[]}
    # If there is significant non-bullet prose (more than a short intro), flag
    extra_prose = [l for l in non_bullets if len(l.strip())>0]
    if len(extra_prose) > 1:
        return {'observed_followed': False,'confidence':'medium','reason':'response not limited to bulleted list','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':f'{len(bullets)} bullets, no table','evidence_refs':[]}
