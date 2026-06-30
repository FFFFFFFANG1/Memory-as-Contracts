def evaluate(trace):
    import re
    trajectory = trace.get('trajectory', []) or []
    tool_calls = trace.get('tool_calls', []) or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls to evaluate.', 'evidence_refs': []}
    # Gather all assistant text content as potential rationale source
    texts = []
    for step in trajectory:
        c = step.get('content') if isinstance(step, dict) else None
        if isinstance(c, str) and c.strip():
            texts.append(c)
    combined = '\n'.join(texts).lower()
    if not combined.strip():
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No written rationale text accompanies tool selections.', 'evidence_refs': []}
    # Heuristic: each tool name (or a clear reference) should appear near justification language and a data-dependency cue
    dep_cues = ['need','require','depend','because','in order to','to obtain','to retrieve','to compute','to determine','uses','based on','input to','feeds','provides','so that','use the','resolve']
    missing = []
    for tc in tool_calls:
        name = (tc.get('name') or '').lower()
        if not name:
            continue
        # find any mention of the tool name in rationale text
        mentioned = name in combined or name.replace('_',' ') in combined
        # check proximity to a dependency cue (within same text block)
        justified = False
        for t in texts:
            tl = t.lower()
            if name in tl or name.replace('_',' ') in tl:
                if any(cue in tl for cue in dep_cues):
                    justified = True
                    break
        if not justified:
            missing.append(name)
    if missing:
        return {'observed_followed': False, 'confidence': 'low', 'reason': f'Tools lacking explicit rationale with data dependency: {sorted(set(missing))}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'low', 'reason': 'Each tool call appears alongside rationale text referencing a dependency cue.', 'evidence_refs': []}
