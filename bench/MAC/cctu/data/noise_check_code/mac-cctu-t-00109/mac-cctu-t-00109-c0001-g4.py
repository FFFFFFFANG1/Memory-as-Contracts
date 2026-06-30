def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'empty response', 'evidence_refs':[]}
    # Find slash pairs like '123/1.23e2' first and mask them out
    pair_pattern = re.compile(r'[-+]?\d[\d,]*(?:\.\d+)?\s*/\s*[-+]?\d+(?:\.\d+)?\s*[\u00d7x*]?\s*10\s*\^?\s*[-+]?\d+|[-+]?\d[\d,]*(?:\.\d+)?\s*/\s*[-+]?\d+(?:\.\d+)?[eE][-+]?\d+')
    pairs = pair_pattern.findall(text)
    masked = pair_pattern.sub(' ', text)
    # find remaining standalone numbers (ignore years-only? keep all numerics with 2+ digits or decimals)
    num_pattern = re.compile(r'(?<![\w/])[-+]?\d[\d,]*(?:\.\d+)?(?![\w/])')
    leftover = [m.group(0) for m in num_pattern.finditer(masked)]
    # filter trivial list markers like '1.' '2.' in enumerations? keep simple: any leftover numeric is a violation
    if not pairs and not leftover:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no numbers detected in response', 'evidence_refs':[]}
    if leftover:
        return {'observed_followed': False, 'confidence':'medium', 'reason': f'numbers not in decimal/scientific slash form: {leftover[:5]}', 'evidence_refs': leftover[:5]}
    return {'observed_followed': True, 'confidence':'high', 'reason': f'{len(pairs)} numeric values follow decimal/scientific slash form', 'evidence_refs': pairs[:5]}
