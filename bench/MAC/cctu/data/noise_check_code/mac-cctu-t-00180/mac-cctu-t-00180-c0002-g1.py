def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    # Find first assistant step containing a numbered roadmap
    def has_roadmap(text):
        if not text: return False
        lines = text.splitlines()
        nums = [l for l in lines if re.match(r'^\s*\d+[\.\)]\s+\S', l)]
        return len(nums) >= 2
    roadmap_idx = None
    for i, step in enumerate(traj):
        content = step.get('content') or ''
        if has_roadmap(content):
            roadmap_idx = i
            break
    if roadmap_idx is None:
        return {'observed_followed': False, 'confidence':'medium','reason':'no numbered roadmap found before tool use','evidence_refs':[]}
    # Check no tool calls before roadmap step
    for j in range(roadmap_idx):
        if traj[j].get('tool_calls'):
            return {'observed_followed': False, 'confidence':'high','reason':'tool call issued before roadmap','evidence_refs':[{'step':j}]}
    # Check roadmap step itself has no tool calls
    if traj[roadmap_idx].get('tool_calls'):
        return {'observed_followed': False, 'confidence':'high','reason':'roadmap turn includes tool calls','evidence_refs':[{'step':roadmap_idx}]}
    return {'observed_followed': True, 'confidence':'high','reason':'roadmap precedes tool calls and no tool call in roadmap turn','evidence_refs':[{'step':roadmap_idx}]}
