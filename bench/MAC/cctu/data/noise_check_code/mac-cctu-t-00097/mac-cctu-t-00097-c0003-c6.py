def evaluate(trace):
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory', 'evidence_refs': []}
    issues = []
    checked = 0
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        content = (step.get('content') or '').strip()
        if not tcs and not content:
            continue
        # Only assess turns that involve tool output reporting
        if tcs:
            checked += 1
            names = [ (tc.get('name') or tc.get('function',{}).get('name') or '') for tc in tcs ]
            if not names:
                continue
            if names[0] != 'biographical_info_retriever':
                # Check if biographical was already called in a prior step of same turn
                issues.append(f'step {i}: first tool is {names[0]}, not biographical_info_retriever')
        elif content:
            # assistant text reporting; look for biographical preface hint
            checked += 1
            low = content.lower()[:300]
            if 'bio' not in low and 'born' not in low and 'biograph' not in low:
                issues.append(f'step {i}: assistant content lacks biographical preface')
    if checked == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no reportable turns', 'evidence_refs': []}
    if issues:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(issues[:3]), 'evidence_refs': issues[:3]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'each turn begins with biographical preface/tool', 'evidence_refs': []}
