def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    final = (trace.get('final_response') or '').lower()
    allowed = 'startup_identifier'
    used = [tc.get('name','') for tc in tool_calls]
    bad = [n for n in used if n and n != allowed]
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used disallowed tools during planning: {bad}', 'evidence_refs': []}
    plan_markers = ['plan', 'step', 'will call', 'tool-call', 'tool call', 'intend to', 'propose']
    has_plan = any(m in final for m in plan_markers)
    landmark_answer_markers = ['the landmark is', 'landmark named', 'identified landmark']
    has_answer = any(m in final for m in landmark_answer_markers)
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to inspect', 'evidence_refs': []}
    if has_answer and not has_plan:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Final response gives landmark answer instead of plan', 'evidence_refs': []}
    if has_plan:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Tool-call plan present and tool usage restricted', 'evidence_refs': []}
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'Could not detect plan markers or landmark answer markers', 'evidence_refs': []}
