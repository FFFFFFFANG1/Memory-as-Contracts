def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no tool calls to evaluate', 'evidence_refs':[]}
    texts = []
    for step in traj:
        c = step.get('content') if isinstance(step, dict) else None
        if isinstance(c, str):
            texts.append(c)
        elif isinstance(c, list):
            for p in c:
                if isinstance(p, dict) and isinstance(p.get('text'), str):
                    texts.append(p['text'])
    joined = '\n'.join(texts)
    obs_open = len(re.findall(r'<observation\b', joined, re.IGNORECASE))
    obs_close = len(re.findall(r'</observation>', joined, re.IGNORECASE))
    n_calls = len(tool_calls)
    # Require at least one <observation> tag per tool call (paired)
    paired = min(obs_open, obs_close)
    has_summary = False
    # Heuristic: look for any non-tag prose after observation tags
    for t in texts:
        stripped = re.sub(r'<observation>.*?</observation>', '', t, flags=re.DOTALL|re.IGNORECASE)
        if len(stripped.strip()) > 20:
            has_summary = True
            break
    followed = paired >= n_calls and has_summary
    return {
        'observed_followed': bool(followed),
        'confidence': 'medium',
        'reason': f'tool_calls={n_calls}, observation_pairs={paired}, has_summary={has_summary}',
        'evidence_refs': []
    }
