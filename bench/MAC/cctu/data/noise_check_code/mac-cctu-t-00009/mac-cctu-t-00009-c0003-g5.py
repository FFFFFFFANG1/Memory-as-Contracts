def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls made; constraint not triggered.', 'evidence_refs': []}
    # Find first tool call iteration/index
    first_idx = None
    for i, step in enumerate(traj):
        if step.get('tool_calls'):
            first_idx = i
            break
    if first_idx is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Could not locate first tool-calling step.', 'evidence_refs': []}
    # Concatenate assistant content before first tool call
    pre_text = ''
    for j in range(first_idx + 1):
        step = traj[j]
        content = step.get('content') or ''
        # For the first tool-calling step, include only its content (the plan should accompany or precede the call)
        pre_text += '\n' + content
    text = pre_text.strip()
    if not text:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No assistant text before first tool invocation; no roadmap present.', 'evidence_refs': []}
    # Check for numbered list (at least 2 numbered items)
    numbered = re.findall(r'(?m)^\s*(?:\d+[\.\)]|\(\d+\))\s+\S', text)
    has_numbered = len(numbered) >= 2
    # Check parallel/batch mention
    parallel_kw = re.search(r'\b(parallel|batch|simultaneous|concurrent|at the same time|in parallel)\b', text, re.I)
    # Count tool names mentioned to ensure roadmap enumerates planned calls
    tool_names = set()
    for tc in tool_calls:
        n = tc.get('name')
        if n: tool_names.add(n)
    mentioned = sum(1 for n in tool_names if n.lower() in text.lower())
    enumerates_all = mentioned >= max(1, len(tool_names))
    if has_numbered and parallel_kw and enumerates_all:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Found numbered roadmap, parallel/batch identification, and all planned tools enumerated before first call.', 'evidence_refs': []}
    missing = []
    if not has_numbered: missing.append('numbered roadmap')
    if not parallel_kw: missing.append('parallel/batch identification')
    if not enumerates_all: missing.append(f'enumeration of all tools ({mentioned}/{len(tool_names)})')
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Missing: ' + ', '.join(missing) + '.', 'evidence_refs': []}
