def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    # Detect population mentions
    pop_pattern = re.compile(r'population[^.\n]{0,200}', re.IGNORECASE)
    matches = pop_pattern.findall(text)
    if not matches:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no population mention found','evidence_refs':[]}
    year_re = re.compile(r'\b(1[89]\d{2}|20\d{2})\b')
    count_re = re.compile(r'\b\d{1,3}(?:[,\.]\d{3})+\b|\b\d{4,}\b|\b\d+(?:\.\d+)?\s*(?:million|billion|thousand)\b', re.IGNORECASE)
    failures = []
    passes = []
    for m in matches:
        has_year = bool(year_re.search(m))
        has_count = bool(count_re.search(m))
        if has_year and has_count:
            passes.append(m[:120])
        else:
            failures.append({'snippet': m[:120], 'has_year': has_year, 'has_count': has_count})
    if failures:
        return {'observed_followed': False, 'confidence':'medium','reason':f'{len(failures)} population mention(s) missing year or raw count','evidence_refs': failures[:3]}
    return {'observed_followed': True, 'confidence':'medium','reason':'all population mentions include count and year','evidence_refs': passes[:3]}
