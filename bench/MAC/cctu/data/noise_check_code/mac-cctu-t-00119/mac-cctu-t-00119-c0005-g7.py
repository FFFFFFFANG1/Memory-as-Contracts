def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Look for a sentence containing 'confidence' and a number
    sentences = re.split(r'(?<=[.!?])\s+', resp)
    conf_sentence = None
    for s in sentences:
        if re.search(r'confidence', s, re.I) and re.search(r'\d', s):
            conf_sentence = s
            break
    has_conf = conf_sentence is not None
    # Find a paragraph >= 400 chars (excluding the confidence sentence)
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', resp) if p.strip()]
    long_para = None
    for p in paragraphs:
        body = p
        if conf_sentence and conf_sentence in body:
            body = body.replace(conf_sentence,'').strip()
        if len(body) >= 400:
            long_para = body
            break
    has_long = long_para is not None
    followed = has_conf and has_long
    reason = f'confidence_sentence={has_conf}, long_paragraph(>=400)={has_long}'
    return {'observed_followed': bool(followed), 'confidence': 'high' if followed else 'medium', 'reason': reason, 'evidence_refs': []}
