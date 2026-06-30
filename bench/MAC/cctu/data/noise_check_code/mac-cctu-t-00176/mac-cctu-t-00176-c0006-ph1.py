def evaluate(trace):
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls observed; cannot assess ordering.', 'evidence_refs': []}
    if not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No trajectory steps available.', 'evidence_refs': []}
    import re
    first = traj[0] if traj else {}
    first_content = (first.get('content') or '') if isinstance(first, dict) else ''
    first_tool_calls = first.get('tool_calls') if isinstance(first, dict) else None
    roadmap_pat = re.compile(r'(sub-?task|decompos|roadmap|plan|step\s*1|1\.|first[, ]|breakdown)', re.I)
    has_roadmap = bool(first_content and roadmap_pat.search(first_content) and len(first_content.strip()) > 40)
    if first_tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'First action included tool calls before any written roadmap.', 'evidence_refs': [{'step': 0}]}
    if not has_roadmap:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'First action did not appear to contain a sub-task decomposition roadmap.', 'evidence_refs': [{'step': 0, 'content_preview': first_content[:160]}]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'First action is a roadmap-like message before any tool invocation.', 'evidence_refs': [{'step': 0, 'content_preview': first_content[:160]}]}
