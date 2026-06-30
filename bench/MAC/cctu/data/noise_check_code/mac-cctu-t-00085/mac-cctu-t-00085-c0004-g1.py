def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        traj = trace.get('trajectory') or []
        parts = []
        for s in traj:
            c = s.get('content') if isinstance(s, dict) else None
            if c: parts.append(c)
        text = '\n\n'.join(parts)
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no write-up text found', 'evidence_refs': []}
    paragraphs = [p for p in re.split(r'\n\s*\n', text.strip()) if p.strip()]
    single_para = len(paragraphs) == 1
    elev_patterns = [
        r'\b\d{1,2}[,.]?\d{3}\s*(?:m|meter|meters|metres|ft|feet|foot)\b',
        r'\b\d{3,5}\s*(?:m|meter|meters|metres|ft|feet|foot)\b',
        r'\belevation[^\n]{0,40}\d',
        r'\bheight[^\n]{0,40}\d',
        r'\baltitude[^\n]{0,40}\d',
    ]
    hits = []
    for pat in elev_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            hits.append(m.group(0))
    range_terms = ['range','ranges','mountains','massif','cordillera','sierra','alps','himalaya','andes','rockies','pyrenees','atlas','caucasus','urals','karakoram','appalachian']
    names_mountains = any(t in text.lower() for t in range_terms)
    followed = single_para and not hits and names_mountains
    reason = f'single_paragraph={single_para}, elevation_hits={hits[:3]}, names_ranges={names_mountains}'
    conf = 'high' if (hits or not single_para) else ('medium' if names_mountains else 'low')
    return {'observed_followed': bool(followed), 'confidence': conf, 'reason': reason, 'evidence_refs': []}
