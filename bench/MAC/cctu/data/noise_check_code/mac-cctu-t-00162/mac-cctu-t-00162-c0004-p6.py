def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    low = text.lower()
    has_gloss = any(k in low for k in ['glossary','indigenous term','native term','local term'])
    # count lines that look like 'term - english' or 'term: english' or 'term (english)'
    patterns = [r'^[\s\-\*\d\.)]*([A-Za-zÀ-ÿ\'’\- ]{2,30})\s*[:\-–—]\s*([A-Za-zÀ-ÿ\- ,]{2,60})$', r'^[\s\-\*\d\.)]*([A-Za-zÀ-ÿ\'’\- ]{2,30})\s*\(([^)]{2,60})\)']
    pair_count = 0
    for line in text.splitlines():
        ls = line.strip()
        if not ls: continue
        for p in patterns:
            if re.match(p, ls):
                pair_count += 1
                break
    followed = has_gloss and pair_count >= 3
    if not has_gloss and pair_count < 3:
        return {'observed_followed': False,'confidence':'medium','reason':'no glossary section or term/english pairs found','evidence_refs':[]}
    return {'observed_followed': bool(followed),'confidence':'medium','reason':f'glossary_marker={has_gloss}, pair_count={pair_count}','evidence_refs':[]}
