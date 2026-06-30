def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    names = [c.get('name') for c in calls]
    first_ok = names[0] == 'cultural_culinary_info'
    bio_count = sum(1 for n in names if n == 'biographical_info_retriever')
    bio_ok = bio_count == 1
    followed = first_ok and bio_ok
    return {'observed_followed': bool(followed), 'confidence': 'high', 'reason': f'first_tool={names[0]}, bio_count={bio_count}', 'evidence_refs': names[:5]}
