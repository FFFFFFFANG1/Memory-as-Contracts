def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = text.splitlines()
    # find first non-empty line
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx >= len(lines):
        return {'observed_followed': False,'confidence':'high','reason':'no content','evidence_refs':[]}
    bullet_re = re.compile(r'^\s*([-*+\u2022]|\d+[.)])\s+\S')
    if not bullet_re.match(lines[idx]):
        return {'observed_followed': False,'confidence':'high','reason':'response does not start with a bullet list','evidence_refs':[lines[idx][:80]]}
    # find end of bullet block
    end = idx
    while end < len(lines) and (bullet_re.match(lines[end]) or not lines[end].strip()):
        end += 1
    bullet_block = '\n'.join(lines[idx:end])
    after_block = '\n'.join(lines[end:])
    # need >=2 bullets to be a 'list'
    bullets = [l for l in lines[idx:end] if bullet_re.match(l)]
    if len(bullets) < 2:
        return {'observed_followed': False,'confidence':'medium','reason':'opening bullet list has fewer than 2 items','evidence_refs':bullets}
    # date detection patterns
    date_patterns = [
        r'\b\d{4}-\d{2}-\d{2}\b',
        r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{4}\b',
        r'\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b',
        r'\b(19|20)\d{2}\b',
    ]
    for pat in date_patterns:
        if re.search(pat, bullet_block, re.IGNORECASE):
            return {'observed_followed': False,'confidence':'medium','reason':'date appears within opening bullet list','evidence_refs':[pat]}
    return {'observed_followed': True,'confidence':'medium','reason':'opens with bullet list before any date','evidence_refs':bullets[:3]}
