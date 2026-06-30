def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    downstream = {'historical_geography_associator', 'biographical_residence_finder'}
    biblio = 'bibliographic_search_tool'
    seq = [(i, c.get('name')) for i, c in enumerate(calls)]
    biblio_indices = [i for i, n in seq if n == biblio]
    downstream_indices = [i for i, n in seq if n in downstream]
    if not downstream_indices:
        if biblio_indices:
            return {'observed_followed': True, 'confidence': 'low', 'reason': 'no downstream geography/residence calls; vacuously satisfied', 'evidence_refs': []}
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no relevant tool usage observed', 'evidence_refs': []}
    if not biblio_indices:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'downstream tools used without any bibliographic retrieval to catalogue', 'evidence_refs': [{'downstream_indices': downstream_indices}]}
    first_downstream = min(downstream_indices)
    late_biblio = [i for i in biblio_indices if i > first_downstream]
    if late_biblio:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'bibliographic_search_tool called at index {late_biblio} after downstream tool at index {first_downstream}; records not catalogued before downstream use', 'evidence_refs': [{'biblio_after_downstream': late_biblio, 'first_downstream': first_downstream}]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'all bibliographic retrievals precede first geography/residence call', 'evidence_refs': [{'biblio_indices': biblio_indices, 'downstream_indices': downstream_indices}]}
