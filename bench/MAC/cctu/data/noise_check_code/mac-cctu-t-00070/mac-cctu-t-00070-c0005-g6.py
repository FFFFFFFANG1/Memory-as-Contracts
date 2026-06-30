def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    m_es = re.search(r'(?im)^[^A-Za-z0-9]*executive summary\b[:\-]*', text)
    m_kf = re.search(r'(?im)^[^A-Za-z0-9]*key findings\b[:\-]*', text)
    if not m_es or not m_kf:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'missing required section header(s)', 'evidence_refs': []}
    if m_es.start() >= m_kf.start():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Executive Summary must precede Key Findings', 'evidence_refs': []}
    es_body = text[m_es.end():m_kf.start()]
    kf_body = text[m_kf.end():]
    def wc(s):
        return len(re.findall(r"\b[\w'-]+\b", s))
    es_w, kf_w = wc(es_body), wc(kf_body)
    if es_w >= 50 or kf_w >= 50:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'section word counts ES={es_w}, KF={kf_w} (need <50)', 'evidence_refs': []}
    if es_w == 0 or kf_w == 0:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'a section appears empty', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'two sections present in order, ES={es_w}w, KF={kf_w}w', 'evidence_refs': []}
