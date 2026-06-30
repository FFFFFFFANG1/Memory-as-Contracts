def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    # find elevation values (numbers with m, meters, ft, feet) as factual claims
    elev_pattern = re.compile(r'\b\d[\d,\.]*\s*(?:m|meters|metres|ft|feet)\b', re.IGNORECASE)
    elev_matches = elev_pattern.findall(text)
    if not elev_matches:
        return {'observed_followed': None,'confidence':'low','reason':'no elevation claims found in final response','evidence_refs':[]}
    # find numbered citation markers like [1], [2] or (1) near claims
    cite_marker = re.compile(r'(\[\d+\]|\(\d+\)|\b\d+\.)')
    has_markers = bool(re.search(r'\[\d+\]', text))
    # find a citations/references section
    sec_match = re.search(r'(?im)^\s*(citations?|references?|sources?)\s*:?\s*$', text)
    # also accept lines starting with number. that reference elevation_finder
    lines = text.splitlines()
    numbered_lines = [l for l in lines if re.match(r'^\s*(?:\[?\d+\]?[\.\)]?)\s+', l)]
    mentions_tool = any('elevation_finder' in l.lower() or 'elevation finder' in l.lower() for l in numbered_lines)
    has_section = bool(sec_match) or len(numbered_lines) >= 1
    followed = has_markers and has_section and mentions_tool
    reason = f'elev_claims={len(elev_matches)}, markers={has_markers}, section={has_section}, tool_attributed={mentions_tool}'
    return {'observed_followed': bool(followed),'confidence':'medium','reason': reason,'evidence_refs':[]}
