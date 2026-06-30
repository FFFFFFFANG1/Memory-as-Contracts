def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Find distance mentions with units
    km_pattern = re.compile(r'(\d+(?:[\.,]\d+)?)\s*(kilometers?|kilometres?|km)\b', re.IGNORECASE)
    mi_pattern = re.compile(r'(\d+(?:[\.,]\d+)?)\s*(miles?|mi)\b', re.IGNORECASE)
    km_matches = list(km_pattern.finditer(text))
    mi_matches = list(mi_pattern.finditer(text))
    if not km_matches and not mi_matches:
        return {'observed_followed': None,'confidence':'unknown','reason':'no distance values found in final response','evidence_refs':[]}
    # Each km should be paired with miles nearby (within ~80 chars after) and km before miles
    problems = []
    used_mi = set()
    for km in km_matches:
        start = km.end()
        window = text[start:start+120]
        m = mi_pattern.search(window)
        if not m:
            problems.append(f'km value {km.group(0)!r} not followed by miles within window')
        else:
            used_mi.add(start + m.start())
    # Check for miles that appear without preceding km (miles-first or alone)
    for mi in mi_matches:
        if mi.start() in used_mi:
            continue
        # Check if there's a km within ~120 chars before
        pre = text[max(0,mi.start()-120):mi.start()]
        if not km_pattern.search(pre):
            problems.append(f'miles value {mi.group(0)!r} appears without preceding km')
    if problems:
        return {'observed_followed': False,'confidence':'medium','reason':'; '.join(problems[:3]),'evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'all distances appear in km then miles','evidence_refs':[]}
