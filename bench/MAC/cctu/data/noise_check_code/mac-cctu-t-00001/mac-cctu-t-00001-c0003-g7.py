def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    low = text.lower()
    # Identify succession records
    succession_markers = ['succession', 'successor', 'succeeded', 'ascended', 'ascension']
    has_succession = any(m in low for m in succession_markers)
    if not has_succession:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no succession record found', 'evidence_refs': []}
    # Look for lineage / ancestral chart indicators
    lineage_markers = ['lineage', 'ancestral', 'ancestry', 'genealog', 'family tree', 'pedigree', 'dynasty chart']
    has_lineage = any(m in low for m in lineage_markers)
    # Look for generation indicators
    gen_terms = ['grandfather', 'grandmother', 'grandparent', 'grandson', 'granddaughter', 'great-grand', 'father', 'mother', 'son', 'daughter']
    gen_count_terms = re.findall(r'generation', low)
    # Count generation-marking relations
    gen_hits = sum(1 for t in gen_terms if t in low)
    explicit_three = bool(re.search(r'(three|3)\s+generation', low))
    if not has_lineage:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no lineage/ancestral chart paired with succession record', 'evidence_refs': []}
    if explicit_three or gen_hits >= 3 or len(gen_count_terms) >= 3:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'lineage with >=3 generation markers present', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'low', 'reason': 'lineage mentioned but <3 generations evident', 'evidence_refs': []}
