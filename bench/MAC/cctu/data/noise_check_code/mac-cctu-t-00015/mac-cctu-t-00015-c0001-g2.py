def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    # Look at the opening portion before first sentence-ending punctuation
    head = re.split(r'(?<=[.!?])\s', resp, maxsplit=1)[0]
    title_terms = ['His Majesty','Her Majesty','His Royal Highness','Her Royal Highness','His Highness','Her Highness','King','Queen','Prince','Princess','Emperor','Empress','Sultan','Tsar','Czar','Archduke','Grand Duke','Duke','Duchess']
    house_markers = ['House of','Dynasty','of the House','Habsburg','Windsor','Bourbon','Romanov','Tudor','Stuart','Hanover','Orange','Saxe','Hohenzollern','Plantagenet','Capet','Valois','Oldenburg','Bernadotte','Glücksburg','Glucksburg','Nassau','Bonaparte','Ottoman','Qing','Ming','Pahlavi','Saud']
    has_title = any(t.lower() in head.lower() for t in title_terms)
    has_house = any(h.lower() in head.lower() for h in house_markers)
    if has_title and has_house:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Opening contains ceremonial title and house/dynasty marker', 'evidence_refs': [head[:200]]}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Missing {"title" if not has_title else ""}{" and " if not has_title and not has_house else ""}{"house affiliation" if not has_house else ""} before factual content', 'evidence_refs': [head[:200]]}
