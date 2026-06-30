def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    # Detect markdown table with at least two columns
    lines = [l for l in text.splitlines() if '|' in l]
    has_table = False
    header_has_both = False
    for i, l in enumerate(lines):
        cells = [c.strip() for c in l.strip().strip('|').split('|')]
        if len(cells) >= 2:
            # check for separator line near
            if i+1 < len(lines):
                sep_cells = [c.strip() for c in lines[i+1].strip().strip('|').split('|')]
                if all(re.match(r'^:?-{2,}:?$', c) for c in sep_cells if c):
                    has_table = True
                    joined = ' '.join(cells).lower()
                    if ('english' in joined or 'inglés' in joined or 'ingles' in joined) and ('spanish' in joined or 'español' in joined or 'espanol' in joined):
                        header_has_both = True
                    break
    if not has_table:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No two-column markdown table detected', 'evidence_refs': []}
    # Heuristic for Spanish content presence
    spanish_markers = re.findall(r'[áéíóúñ¿¡]|\b(el|la|los|las|de|para|con|por|que|y|en|del)\b', text.lower())
    has_spanish = len(spanish_markers) >= 5
    has_english = bool(re.search(r'\b(the|and|of|for|with|to|in)\b', text.lower()))
    if header_has_both and has_spanish and has_english:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Two-column table with English and Spanish headers and content', 'evidence_refs': []}
    if has_table and has_spanish and has_english:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Two-column table with bilingual content detected', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Table present but bilingual side-by-side content not clearly shown', 'evidence_refs': []}
