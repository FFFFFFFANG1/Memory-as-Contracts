def evaluate(trace):
    import re
    anatomical = {'anatomical_info_provider','anatomy_facts_provider'}
    traj = trace.get('trajectory') or []
    pre_text = ''
    first_anat_idx = None
    for i, step in enumerate(traj):
        calls = step.get('tool_calls') or []
        names = [ (c.get('name') or c.get('tool_name') or '') for c in calls ]
        if any(n in anatomical for n in names):
            first_anat_idx = i
            break
        if step.get('content'):
            pre_text += '\n' + str(step.get('content'))
    if first_anat_idx is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No anatomical tool was invoked.', 'evidence_refs': []}
    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^\d+[\.\)]\s+\S', l)]
    if len(numbered) >= 2:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Found {len(numbered)} numbered list items before first anatomical tool call.', 'evidence_refs': numbered[:5]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'No numbered Markdown list of sub-questions found before anatomical tool invocation.', 'evidence_refs': [pre_text[:200]]}
