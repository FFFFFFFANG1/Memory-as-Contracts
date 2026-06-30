def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    casualty_kw = r'(?:killed|deaths?|dead|casualt(?:y|ies)|wounded|injured|fatalit(?:y|ies)|perished|victims?)'
    # Find casualty count mentions: a number near a casualty keyword
    num = r'(?:\d{1,3}(?:[,\d]{0,12})|\d+(?:\.\d+)?\s*(?:million|thousand|hundred|billion))'
    pattern = re.compile(r'(' + num + r')\s+(?:\w+\s+){0,3}?' + casualty_kw + r'|' + casualty_kw + r'\s*[:\-]?\s*(' + num + r')', re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if not matches:
        return {'observed_followed': None, 'confidence':'low','reason':'no casualty count detected in final response','evidence_refs':[]}
    confidence_pat = re.compile(r'\(\s*(?:~|approx\.?|about)?\s*\d{1,3}\s*%\s*(?:confidence|conf\.?|certainty)?\s*\)', re.IGNORECASE)
    missing = []
    for m in matches:
        end = m.end()
        window = text[end:end+80]
        if not confidence_pat.search(window):
            missing.append(m.group(0))
    if missing:
        return {'observed_followed': False, 'confidence':'medium','reason':'casualty counts without confidence% appended: ' + '; '.join(missing[:3]),'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium','reason':'all casualty counts have confidence percentage in parentheses','evidence_refs':[]}
