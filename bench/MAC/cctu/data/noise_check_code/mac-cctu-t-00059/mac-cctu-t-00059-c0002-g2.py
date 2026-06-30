def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '')
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    # Look at the prefix area (first ~40% or first 2000 chars)
    prefix = resp[:max(2000, len(resp)//2)]
    levels = ['kingdom', 'phylum', 'division', 'class', 'order', 'family', 'genus', 'species']
    low = prefix.lower()
    found = [lv for lv in levels if re.search(r'\b' + lv + r'\b', low)]
    # Required: kingdom and species at minimum, plus most others
    has_kingdom = 'kingdom' in found
    has_species = 'species' in found
    has_phylum_or_div = ('phylum' in found) or ('division' in found)
    core = ['class', 'order', 'family', 'genus']
    core_count = sum(1 for c in core if c in found)
    if not has_kingdom or not has_species:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Response prefix lacks kingdom and/or species labels', 'evidence_refs': [prefix[:200]]}
    if not has_phylum_or_div or core_count < 3:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Prefix missing taxonomic levels; found={found}', 'evidence_refs': [prefix[:200]]}
    # Heuristic: check the taxonomic block appears at the very start
    starts_well = bool(re.match(r'\s*(\*+|#+|-|\d|[A-Za-z])', resp)) and low.find('kingdom') < 500
    if not starts_well:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Taxonomy not at start of response', 'evidence_refs': [resp[:200]]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Prefix contains taxonomic levels: {found}', 'evidence_refs': [prefix[:300]]}
