def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Find scientific name patterns: (Genus species) - capitalized genus + lowercase species in parens
    sci_pattern = re.compile(r'\(([A-Z][a-z]+(?:\s+[a-z]+(?:\s+[a-z]+)?))\)')
    matches = sci_pattern.findall(text)
    if not matches:
        return {'observed_followed': False, 'confidence':'low','reason':'no scientific names in parentheses found','evidence_refs':[]}
    # Check each match is preceded by a word (vernacular name)
    violations = []
    good = 0
    for m in re.finditer(r'(\S+)\s*\(([A-Z][a-z]+(?:\s+[a-z]+){1,2})\)', text):
        preceding = m.group(1)
        # preceding should be a word, not punctuation only
        if re.search(r'[A-Za-zÀ-ÿ]', preceding):
            good += 1
        else:
            violations.append(m.group(0))
    if good == 0:
        return {'observed_followed': False,'confidence':'medium','reason':'scientific names not preceded by vernacular names','evidence_refs':[]}
    if violations:
        return {'observed_followed': False,'confidence':'low','reason':f'some entries lack vernacular: {violations[:3]}','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'low','reason':f'found {good} species with vernacular (scientific) pattern; regional language not verifiable','evidence_refs':[]}
