def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    if len(paragraphs) < 3:
        return {'observed_followed': False, 'confidence':'high','reason':f'found {len(paragraphs)} paragraphs, need 3','evidence_refs':[]}
    if len(paragraphs) > 3:
        return {'observed_followed': False, 'confidence':'medium','reason':f'found {len(paragraphs)} paragraphs, expected exactly 3','evidence_refs':[]}
    joined = ' \n '.join(paragraphs).lower()
    origin_terms = ['origin','originated','began','history','historical','root','ancient','first']
    meaning_terms = ['meaning','symbol','represent','signif','denote','stands for','convey']
    modern_terms = ['modern','today','contemporary','currently','present','nowadays','recent']
    has_origin = any(t in joined for t in origin_terms)
    has_meaning = any(t in joined for t in meaning_terms)
    has_modern = any(t in joined for t in modern_terms)
    missing = [n for n,v in [('origin',has_origin),('meaning',has_meaning),('modern usage',has_modern)] if not v]
    if missing:
        return {'observed_followed': False, 'confidence':'medium','reason':'missing coverage: '+', '.join(missing),'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium','reason':'three paragraphs covering origin, meaning, modern usage','evidence_refs':[]}
