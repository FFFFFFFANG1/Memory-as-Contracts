def evaluate(trace):
    import re
    texts = []
    for step in trace.get('trajectory', []) or []:
        c = step.get('content')
        if isinstance(c, str) and c.strip():
            texts.append(c)
    fr = trace.get('final_response')
    if isinstance(fr, str) and fr.strip():
        texts.append(fr)
    if not texts:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No textual outputs found', 'evidence_refs': []}
    bullet_re = re.compile(r'^\s*(?:[-*+•]\s+|\d+[.)]\s+)', re.MULTILINE)
    table_re = re.compile(r'^\s*\|.*\|\s*$', re.MULTILINE)
    sep_re = re.compile(r'^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$', re.MULTILINE)
    offenders = []
    for i, t in enumerate(texts):
        bm = bullet_re.findall(t)
        tm = table_re.findall(t)
        sm = sep_re.findall(t)
        if len(bm) >= 2 or sm or len(tm) >= 2:
            offenders.append({'index': i, 'bullets': len(bm), 'table_rows': len(tm), 'separators': len(sm)})
    if offenders:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Detected bullet-list or tabular formatting in outputs', 'evidence_refs': offenders}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'No bullet lists or tables detected; appears to be prose', 'evidence_refs': []}
