def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {'observed_followed': False,'confidence':'high','reason':'no content lines','evidence_refs':[]}
    bullet_re = re.compile(r'^\s*([-*\u2022])\s+')
    contents = []
    for ln in lines:
        m = bullet_re.match(ln)
        if not m:
            return {'observed_followed': False,'confidence':'high','reason': 'line is not a bullet: ' + ln[:60],'evidence_refs':[]}
        contents.append(ln[m.end():])
    if len(contents) < 1:
        return {'observed_followed': False,'confidence':'high','reason':'no bullets found','evidence_refs':[]}
    forbidden = set('.;:!?"\'()[]{}/\\|<>~`@#$%^&*_=+')
    for c in contents:
        for ch in c:
            if ch in forbidden:
                return {'observed_followed': False,'confidence':'high','reason': 'forbidden punctuation ' + ch + ' in: ' + c[:60],'evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':'single bullet list, only commas as inline punctuation','evidence_refs':[]}
