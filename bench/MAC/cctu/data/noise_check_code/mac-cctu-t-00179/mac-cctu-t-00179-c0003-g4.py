def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    low = text.lower()
    # Check for kilogram usage in comparative context
    kg_pat = re.compile(r'\b\d[\d,\.]*\s*(kg|kgs|kilograms?|kilogrammes?)\b', re.I)
    kg_hits = kg_pat.findall(low)
    # Check metric tons mentioned
    ton_pat = re.compile(r'\b\d[\d,\.]*\s*(metric tons?|tonnes?|tons?|mt)\b', re.I)
    ton_hits = ton_pat.findall(low)
    # Species count detection: look for 'species' near numbers
    species_ctx = re.findall(r'([^.\n]*\bspecies\b[^.\n]*)', low)
    exact_species = []
    range_species = []
    for s in species_ctx:
        # range patterns: 'X to Y', 'X-Y', 'between X and Y', 'approximately', 'around'
        if re.search(r'\b\d+\s*(?:-|–|to)\s*\d+\b', s) or re.search(r'between\s+\d+\s+and\s+\d+', s) or re.search(r'(approximately|around|roughly|about|over|more than|fewer than|less than)\s+\d+', s):
            range_species.append(s.strip())
        elif re.search(r'\b\d+\b', s):
            exact_species.append(s.strip())
    issues = []
    if kg_hits:
        issues.append(f'kilogram units used: {kg_hits[:3]}')
    if exact_species:
        issues.append(f'exact species counts: {exact_species[:3]}')
    has_comparative_numeric = bool(kg_hits or ton_hits)
    has_species_numeric = bool(exact_species or range_species)
    if not has_comparative_numeric and not has_species_numeric:
        return {'observed_followed': None, 'confidence':'low','reason':'no comparative weights or species counts found','evidence_refs':[]}
    if issues:
        return {'observed_followed': False, 'confidence':'high','reason':'; '.join(issues),'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium','reason':'weights in tons and/or species as ranges','evidence_refs':[]}
