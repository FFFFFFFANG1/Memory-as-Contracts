def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Find all standalone numbers (digit sequences) in the text
    numbers = list(re.finditer(r'\d+', text))
    if not numbers:
        return {'observed_followed': None, 'confidence':'low','reason':'no numeric values present to evaluate','evidence_refs':[]}
    bad = []
    good = []
    for m in numbers:
        s, e = m.start(), m.end()
        # number must be wrapped in parentheses: char before '(' and after ')'
        before = text[max(0,s-1):s]
        after = text[e:e+1]
        if before != '(' or after != ')':
            bad.append(m.group())
            continue
        # check that something word-like precedes the '('
        pre = text[:s-1].rstrip()
        wm = re.search(r'([A-Za-z\-]+)\s*$', pre)
        if not wm:
            bad.append(m.group())
        else:
            good.append((wm.group(1), m.group()))
    if bad:
        return {'observed_followed': False, 'confidence':'high','reason': f'numeric values not preceded by spelled-out form in parentheses: {bad[:5]}','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason': f'all numeric values formatted as words followed by figure in parentheses: {good[:5]}','evidence_refs':[]}
