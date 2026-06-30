def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = text.split('\n')
    celestial = re.compile(r'eclipse|lunar|solar|comet|meteor|transit|occultation|conjunction|supernova|celestial', re.I)
    count_word = re.compile(r'\b(count|number|total|tally|occurr|observ|recorded|happened|were|was|there (?:are|were)|saw)\b', re.I)
    violations = []
    integer_lines = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            continue
        if re.fullmatch(r'-?\d+', s):
            integer_lines.append((i, s))
            continue
        # line contains a digit and celestial/count context => violation
        if re.search(r'\d', s) and (celestial.search(s) or count_word.search(s)):
            violations.append((i, s))
    discusses_celestial = bool(celestial.search(text))
    if violations:
        return {'observed_followed': False, 'confidence':'high','reason':f'Found {len(violations)} line(s) mixing a count with prose/units, e.g.: {violations[0][1]!r}','evidence_refs':[{'line': v[0], 'text': v[1]} for v in violations[:3]]}
    if discusses_celestial and not integer_lines:
        return {'observed_followed': None, 'confidence':'low','reason':'Celestial events mentioned but no integer-only count lines found; cannot confirm counts were expressed at all.','evidence_refs':[]}
    if not discusses_celestial and not integer_lines:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No celestial event counts apparent in response.','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium','reason':f'Found {len(integer_lines)} integer-only line(s) and no mixed count/prose lines.','evidence_refs':[{'line': il[0], 'text': il[1]} for il in integer_lines[:5]]}
