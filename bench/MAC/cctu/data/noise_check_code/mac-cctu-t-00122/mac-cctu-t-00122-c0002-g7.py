def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Fewer than two non-empty lines; cannot have separate language lines', 'evidence_refs': []}
    spanish_markers = ['á','é','í','ó','ú','ñ','¿','¡',' el ',' la ',' los ',' las ',' de ',' inventario',' biblioteca',' almacenamiento',' libros',' está',' capacidad',' disponible',' espa',' y ']
    english_markers = [' the ',' is ',' are ',' inventory',' library',' storage',' books',' available',' capacity',' and ',' of ',' has ',' currently']
    def score(line, markers):
        low = ' ' + line.lower() + ' '
        return sum(1 for m in markers if m in low)
    has_es = any(score(l, spanish_markers) >= 1 for l in lines)
    has_en = any(score(l, english_markers) >= 1 for l in lines)
    if has_es and has_en:
        # ensure they're on different lines
        es_lines = [i for i,l in enumerate(lines) if score(l, spanish_markers) >= 1]
        en_lines = [i for i,l in enumerate(lines) if score(l, english_markers) >= 1 and score(l, spanish_markers) == 0]
        if en_lines and es_lines and set(en_lines) != set(es_lines):
            return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Detected English and Spanish content on separate lines', 'evidence_refs': []}
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'Languages not clearly separated on distinct lines', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Missing language version (en={has_en}, es={has_es})', 'evidence_refs': []}
