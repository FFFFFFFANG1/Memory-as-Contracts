def evaluate(trace):
    final = (trace.get('final_response') or '').strip()
    calls = trace.get('tool_calls') or []
    count = sum(1 for c in calls if (c.get('name') or '') == 'forest_tree_data_retriever')
    ends_ok = final.endswith('[CENSUS-OK]')
    if not calls and not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no evidence', 'evidence_refs': []}
    followed = (count >= 2) and ends_ok
    return {'observed_followed': bool(followed), 'confidence': 'high', 'reason': f'forest_tree_data_retriever calls={count}, ends_with_token={ends_ok}', 'evidence_refs': []}
