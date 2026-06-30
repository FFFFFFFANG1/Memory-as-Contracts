def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    fences = re.findall(r'```[\s\S]*?```|~~~[\s\S]*?~~~', resp)
    if not fences:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no fenced code block present', 'evidence_refs': []}
    last_fence = fences[-1]
    idx = resp.rfind(last_fence)
    above = resp[:idx].strip()
    if not above:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'fenced block has no user-facing answer above it', 'evidence_refs': []}
    tool_calls = trace.get('tool_calls') or []
    arg_keys = set()
    for tc in tool_calls:
        args = tc.get('arguments') or {}
        if isinstance(args, dict):
            for k in args.keys():
                arg_keys.add(str(k))
    fence_text = last_fence.lower()
    missing_args = [k for k in arg_keys if k.lower() not in fence_text]
    if arg_keys and len(missing_args) > len(arg_keys) / 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'fenced block missing many tool argument names: {missing_args}', 'evidence_refs': []}
    has_enumeration = bool(re.search(r'(argument|field|param|json)', fence_text, re.I))
    if not has_enumeration:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'fenced block does not enumerate arguments/fields', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'fenced scratchpad block present below answer with argument/field enumeration', 'evidence_refs': []}
