def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    # check for bullets / list markers
    bullet_pat = re.compile(r'(^|\n)\s*([\-\*\u2022\u00b7]|\d+\.)\s+')
    if bullet_pat.search(text):
        return {'observed_followed': False,'confidence':'high','reason':'contains bullet or list markers','evidence_refs':[text[:200]]}
    # check single sentence: split on sentence-ending punctuation followed by space/end
    # remove trailing punctuation then ensure no internal '. '
    stripped = text.rstrip()
    # Count sentence terminators not at end
    inner = stripped[:-1] if stripped and stripped[-1] in '.!?' else stripped
    if re.search(r'[\.!?]\s+\S', inner):
        return {'observed_followed': False,'confidence':'high','reason':'more than one sentence','evidence_refs':[text[:200]]}
    if '\n' in stripped:
        return {'observed_followed': False,'confidence':'high','reason':'multi-line response suggests per-species line items','evidence_refs':[text[:200]]}
    # check numerical difference present
    if not re.search(r'\d', text):
        return {'observed_followed': False,'confidence':'medium','reason':'no numeric value indicating difference','evidence_refs':[text[:200]]}
    return {'observed_followed': True,'confidence':'medium','reason':'single sentence without bullets containing a number','evidence_refs':[text[:200]]}
