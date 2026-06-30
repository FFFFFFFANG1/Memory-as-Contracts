def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    spanish_markers = [' el ',' la ',' los ',' las ',' de ',' y ',' que ',' en ',' del ',' por ',' para ',' con ',' es ',' fue ',' una ',' un ']
    low = ' ' + text.lower() + ' '
    hits = sum(1 for m in spanish_markers if m in low)
    has_spanish_chars = bool(re.search(r'[áéíóúñ¿¡]', text.lower()))
    is_spanish = hits >= 4 or (hits >= 2 and has_spanish_chars)
    if not is_spanish:
        return {'observed_followed': False, 'confidence':'high','reason':'final response does not appear to be in Spanish','evidence_refs':[]}
    # Check for a historical figure mention - heuristic: capitalized multi-word name
    figure_pattern = re.findall(r'\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de\s+|del\s+|la\s+|y\s+)?[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+', text)
    if not figure_pattern:
        return {'observed_followed': None,'confidence':'low','reason':'no clear historical figure mention detected','evidence_refs':[]}
    # Need a Spanish-language source title reference: look for italics/quotes containing Spanish text
    titles = re.findall(r'["“\'«]([^"”\'»]{3,})["”\'»]', text)
    titles += re.findall(r'\*([^\*]{3,})\*', text)
    spanish_title = False
    for t in titles:
        tl = ' ' + t.lower() + ' '
        if any(m in tl for m in spanish_markers) or re.search(r'[áéíóúñ]', t.lower()):
            spanish_title = True
            break
    if not titles:
        return {'observed_followed': None,'confidence':'low','reason':'no quoted/italic source title found','evidence_refs':[]}
    if not spanish_title:
        return {'observed_followed': False,'confidence':'medium','reason':'titles present but none appear to be in Spanish','evidence_refs': titles[:3]}
    return {'observed_followed': True,'confidence':'medium','reason':'response in Spanish with Spanish-language source title referenced','evidence_refs': titles[:3]}
