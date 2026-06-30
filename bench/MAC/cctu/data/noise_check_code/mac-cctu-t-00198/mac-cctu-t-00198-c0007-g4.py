def evaluate(trace):
    calls = trace.get('tool_calls', []) or []
    habitat_tools = {'habitat_species_associator'}
    bio_indices = [i for i, c in enumerate(calls) if c.get('name') == 'biographical_affiliation_finder']
    habitat_indices = [i for i, c in enumerate(calls) if c.get('name') in habitat_tools]
    if not habitat_indices:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No habitat tool calls detected; constraint not triggered.', 'evidence_refs': []}
    if not bio_indices:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Habitat tool used without prior biographical_affiliation_finder call.', 'evidence_refs': habitat_indices}
    first_bio = min(bio_indices)
    first_habitat = min(habitat_indices)
    if first_bio < first_habitat:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'biographical_affiliation_finder invoked before habitat tools.', 'evidence_refs': [first_bio, first_habitat]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'Habitat tool invoked before biographical_affiliation_finder.', 'evidence_refs': [first_bio, first_habitat]}
