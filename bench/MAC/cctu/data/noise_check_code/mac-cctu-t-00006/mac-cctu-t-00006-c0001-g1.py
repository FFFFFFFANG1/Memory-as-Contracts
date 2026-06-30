def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Check single paragraph: no blank line separators
    if re.search(r'\n\s*\n', text):
        return {'observed_followed': False, 'confidence':'high','reason':'multiple paragraphs detected (blank line separator)','evidence_refs':[]}
    # Check no list/bullet/numbered markers
    lines = [ln for ln in text.split('\n') if ln.strip()]
    bullet_re = re.compile(r'^\s*([-*+\u2022]|\d+[\.)])\s+')
    bullets = [ln for ln in lines if bullet_re.match(ln)]
    if bullets:
        return {'observed_followed': False, 'confidence':'high','reason':'list/bullet structure found','evidence_refs':bullets[:3]}
    # Check no headings
    if any(re.match(r'^\s*#{1,6}\s+', ln) for ln in lines):
        return {'observed_followed': False, 'confidence':'high','reason':'markdown heading found','evidence_refs':[]}
    # Check it reads as prose (has sentence punctuation)
    if not re.search(r'[\.!?]', text):
        return {'observed_followed': False, 'confidence':'medium','reason':'no sentence-ending punctuation, may not be prose','evidence_refs':[]}
    # Many lines but no blank separator could still be one paragraph with soft wraps; accept
    return {'observed_followed': True, 'confidence':'high','reason':'single prose paragraph','evidence_refs':[]}
