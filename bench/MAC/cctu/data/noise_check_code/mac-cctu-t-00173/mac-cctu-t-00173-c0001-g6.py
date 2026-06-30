def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    final = (trace.get('final_response') or '').lower()
    traj = trace.get('trajectory') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    # Group tool calls by what entity/topic they query - approximate by arguments
    names = [tc.get('name','') for tc in tool_calls]
    # Heuristic: look for repeated lookups across different tools
    # Find pairs of calls with overlapping argument values but different tool names
    def args_values(a):
        if isinstance(a, dict):
            return [str(v).lower() for v in a.values()]
        return [str(a).lower()]
    cross_tool_repeats = []
    for i, tc in enumerate(tool_calls):
        vals_i = args_values(tc.get('arguments') or {})
        for j in range(i+1, len(tool_calls)):
            tc2 = tool_calls[j]
            if tc.get('name') == tc2.get('name'):
                continue
            vals_j = args_values(tc2.get('arguments') or {})
            overlap = set(vals_i) & set(vals_j)
            overlap = {v for v in overlap if len(v) > 2}
            if overlap:
                cross_tool_repeats.append((i,j,tc.get('name'),tc2.get('name'),list(overlap)))
    if cross_tool_repeats:
        return {'observed_followed': True, 'confidence':'medium','reason':f'found {len(cross_tool_repeats)} cross-tool repeated lookups suggesting verification','evidence_refs':[{'pairs':cross_tool_repeats[:5]}]}
    # Check if any verification mention in trajectory text
    text_blob = ' '.join((s.get('content') or '') for s in traj).lower()
    if 'verif' in text_blob or 'confirm' in text_blob or 'cross-check' in text_blob or 'double-check' in text_blob:
        return {'observed_followed': False, 'confidence':'low','reason':'verification mentioned but no alternative-tool repeat of numeric lookup detected','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'low','reason':'no alternative-tool re-lookup detected for any value','evidence_refs':[]}
