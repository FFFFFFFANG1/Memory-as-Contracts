def evaluate(trace):
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    first = traj[0]
    content = (first.get('content') or '').strip()
    tool_calls = first.get('tool_calls') or []
    if tool_calls:
        return {'observed_followed': False,'confidence':'high','reason':'first turn issued tool calls','evidence_refs':[{'turn':0,'tool_calls':[t.get('name') for t in tool_calls]}]}
    if not content:
        return {'observed_followed': False,'confidence':'high','reason':'first turn empty, no roadmap','evidence_refs':[]}
    import re
    text = content.lower()
    roadmap_terms = ['roadmap','sub-task','subtask','sub task','plan','steps','step 1','outline']
    has_term = any(t in text for t in roadmap_terms)
    has_list = bool(re.search(r'(^|\n)\s*(\d+[.)]|[-*])\s+', content))
    if has_term or has_list:
        return {'observed_followed': True,'confidence':'medium','reason':'first turn contains roadmap-like written plan before tool calls','evidence_refs':[{'turn':0,'snippet':content[:200]}]}
    return {'observed_followed': False,'confidence':'low','reason':'first turn lacks roadmap indicators','evidence_refs':[{'turn':0,'snippet':content[:200]}]}
