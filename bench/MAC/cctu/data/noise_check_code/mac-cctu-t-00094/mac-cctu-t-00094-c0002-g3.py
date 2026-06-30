def evaluate(trace):
    calls = trace.get('tool_calls') or []
    names = [c.get('name') for c in calls]
    if 'industrial_production_analyzer' not in names:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No industrial_production_analyzer calls present.', 'evidence_refs': []}
    ok = True
    refs = []
    for i, n in enumerate(names):
        if n == 'industrial_production_analyzer':
            follow = names[i+1:]
            if 'teaching_approach_evaluator' not in follow:
                ok = False
                refs.append({'index': i, 'name': n})
                break
    if ok:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Each industrial_production_analyzer call is followed by teaching_approach_evaluator.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'industrial_production_analyzer call not followed by teaching_approach_evaluator.', 'evidence_refs': refs}
