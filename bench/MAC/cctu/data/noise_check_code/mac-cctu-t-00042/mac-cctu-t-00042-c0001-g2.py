def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Find list patterns: 3+ items joined by commas ending with 'and'/'or'
    # Look for ', and' or ', or' (Oxford) vs ' and' / ' or' without preceding comma after a list
    pattern = re.compile(r'((?:[^,\n.;:!?]+,\s+){1,}[^,\n.;:!?]+\s+(and|or)\s+[^,\n.;:!?]+)', re.IGNORECASE)
    matches = pattern.findall(text)
    if not matches:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no multi-entity list detected','evidence_refs':[]}
    violations = []
    passes = []
    for m, conj in matches:
        # Check if there's a comma right before the final ' and'/' or'
        idx = m.lower().rfind(' '+conj.lower()+' ')
        if idx <= 0:
            continue
        before = m[:idx].rstrip()
        if before.endswith(','):
            passes.append(m)
        else:
            violations.append(m)
    if not passes and not violations:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no qualifying list','evidence_refs':[]}
    if violations:
        return {'observed_followed': False, 'confidence':'high','reason':'missing Oxford comma in list(s): '+ '; '.join(violations[:3]),'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':'Oxford comma present in detected list(s)','evidence_refs':[]}
