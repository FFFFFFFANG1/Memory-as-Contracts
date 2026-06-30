def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # find a sentence containing 'confidence' and a number
    sentences = re.split(r'(?<=[.!?])\s+', text)
    conf_sentence = None
    for s in sentences:
        if 'confidence' in s.lower() and re.search(r'\d', s):
            conf_sentence = s
            break
    has_conf = conf_sentence is not None
    # find a commentary paragraph >= 400 chars
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    long_para = any(len(p) >= 400 for p in paragraphs)
    if has_conf and long_para:
        return {'observed_followed': True, 'confidence':'high','reason':'numeric confidence sentence and >=400 char paragraph present','evidence_refs':[]}
    missing = []
    if not has_conf: missing.append('numeric confidence sentence')
    if not long_para: missing.append('>=400 char commentary paragraph')
    return {'observed_followed': False, 'confidence':'high','reason':'missing: '+', '.join(missing),'evidence_refs':[]}
