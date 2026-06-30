def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # find candidate list lines (bullets, numbered, or lines containing a 4-digit year)
    entries = []
    for l in lines:
        m = re.match(r'^(?:[-*\u2022]|\d+[.)])\s*(.+)$', l)
        content = m.group(1) if m else l
        year_match = re.search(r'\b(1[89]\d{2}|20\d{2})\b', content)
        # extract leading org name (before colon, dash, or parenthesis)
        name_match = re.match(r'^([A-Z][^:\-\(\u2013\u2014]{1,80}?)(?:\s*[:\-\(\u2013\u2014]|$)', content)
        if year_match and name_match:
            entries.append((name_match.group(1).strip().lower(), year_match.group(1), l))
    if len(entries) < 2:
        return {'observed_followed': None,'confidence':'low','reason':'could not identify list of orgs with years','evidence_refs':[]}
    names = [e[0] for e in entries]
    sorted_names = sorted(names)
    alpha_ok = names == sorted_names
    annotated_ok = all(e[1] for e in entries)
    followed = alpha_ok and annotated_ok
    return {'observed_followed': bool(followed),'confidence':'medium','reason':f'alpha_ok={alpha_ok}, annotated_ok={annotated_ok}, names={names}','evidence_refs':[e[2] for e in entries]}
