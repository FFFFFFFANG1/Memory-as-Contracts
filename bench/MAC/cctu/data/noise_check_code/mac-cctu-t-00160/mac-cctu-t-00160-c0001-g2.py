def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    names = [c.get('name') for c in calls]
    first_ok = names[0] == 'plant_characteristics_analyzer'
    bio_count = sum(1 for n in names if n == 'comprehensive_biographical_info_retriever')
    bio_ok = bio_count <= 1
    if first_ok and bio_ok:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'first tool is plant_characteristics_analyzer; bio retriever used {bio_count} time(s)', 'evidence_refs': []}
    reasons = []
    if not first_ok:
        reasons.append(f'first tool was {names[0]}, not plant_characteristics_analyzer')
    if not bio_ok:
        reasons.append(f'comprehensive_biographical_info_retriever used {bio_count} times')
    return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
