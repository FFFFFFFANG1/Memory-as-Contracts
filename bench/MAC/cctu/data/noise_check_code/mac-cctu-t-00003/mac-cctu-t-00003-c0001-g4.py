def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Find numeric tokens that could be vote counts: numbers with commas, or integers >= 1000
    num_pattern = re.compile(r'(?<![\w.])(\d{1,3}(?:,\d{3})+|\d{4,})(?![\d.,]*\s*%)')
    pct_pattern = re.compile(r'\d+(?:\.\d+)?\s*%')
    lines = [l for l in re.split(r'(?<=[\.\n])', text) if l.strip()]
    violations = []
    has_any_numeric = False
    for line in lines:
        nums = num_pattern.findall(line)
        if not nums:
            continue
        has_any_numeric = True
        pcts = pct_pattern.findall(line)
        if not pcts:
            violations.append(line.strip()[:160])
    # Also check inverse: percentages without absolute counts on same line
    for line in lines:
        pcts = pct_pattern.findall(line)
        if not pcts:
            continue
        # check for absolute count (number not directly followed by %)
        abs_nums = re.findall(r'(?<![\w.])(\d{1,3}(?:,\d{3})+|\d{3,})(?!\s*%)', line)
        if not abs_nums:
            has_any_numeric = True
            violations.append('pct without abs: '+line.strip()[:160])
    if not has_any_numeric:
        return {'observed_followed': None, 'confidence':'low','reason':'no numeric electoral results detected','evidence_refs':[]}
    if violations:
        return {'observed_followed': False, 'confidence':'medium','reason':'numeric results missing paired count/percentage','evidence_refs':violations[:5]}
    return {'observed_followed': True, 'confidence':'medium','reason':'numeric results appear paired with percentages','evidence_refs':[]}
