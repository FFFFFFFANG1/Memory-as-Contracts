def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    # Collect assistant text emitted before the first tool call
    pre_text_parts = []
    first_tool_seen = False
    for step in traj:
        calls = step.get('tool_calls') or []
        content = step.get('content') or ''
        if not first_tool_seen:
            if content:
                pre_text_parts.append(content)
            if calls:
                first_tool_seen = True
                break
        else:
            break
    pre_text = '\n'.join(pre_text_parts)
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trajectory; cannot judge pre-call inventory requirement.', 'evidence_refs': []}
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No assistant text precedes the first tool call, so no inventory was written.', 'evidence_refs': []}
    low = pre_text.lower()
    # Heuristic: must mention input/schema/argument terms AND output/return terms, and enumerate multiple tools
    input_terms = ['input', 'schema', 'argument', 'parameter', 'param']
    output_terms = ['output', 'return', 'result', 'shape', 'response']
    has_input = any(t in low for t in input_terms)
    has_output = any(t in low for t in output_terms)
    # Count how many distinct tool names appear in pre_text
    tool_names = set()
    for tc in tool_calls:
        n = tc.get('name')
        if n: tool_names.add(n)
    # Use available tools mentioned in pre_text as inventory signal
    mentioned = [n for n in tool_names if n and n.lower() in low]
    inventory_breadth = len(mentioned) >= max(1, len(tool_names))
    followed = has_input and has_output and inventory_breadth
    reason = f'pre_text has_input={has_input}, has_output={has_output}, tools_mentioned={len(mentioned)}/{len(tool_names)}'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
