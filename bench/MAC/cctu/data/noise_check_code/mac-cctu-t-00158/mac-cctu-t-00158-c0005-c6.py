def evaluate(trace):
    import re
    trajectory = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    # Find first assistant step containing a numbered roadmap (>=2 numbered items)
    roadmap_iter = None
    for step in trajectory:
        content = (step.get('content') or '') if isinstance(step, dict) else ''
        nums = re.findall(r'(?m)^\s*(\d+)[\.\)]\s+\S', content)
        if len(nums) >= 2:
            roadmap_iter = step.get('iteration', step.get('index'))
            break
    if roadmap_iter is None:
        # No roadmap found; if no tool calls either, unknown
        if not tool_calls:
            return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No roadmap and no tool calls observed.', 'evidence_refs': []}
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No numbered roadmap detected before retrieval tool calls.', 'evidence_refs': []}
    # Check no tool call occurred before roadmap_iter
    for tc in tool_calls:
        it = tc.get('iteration', tc.get('index'))
        if it is None:
            continue
        if it < roadmap_iter:
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'Tool {tc.get("name")} called at iter {it} before roadmap at iter {roadmap_iter}.', 'evidence_refs': [str(tc.get('name'))]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Numbered roadmap present before any retrieval tool invocation.', 'evidence_refs': [f'roadmap_iter={roadmap_iter}']}
