def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    # Check tool ordering
    if not tool_calls:
        first_ok = None
    else:
        first_ok = tool_calls[0].get('name') == 'island_beach_finder'
    # Check numbered list format
    lines = [l.strip() for l in final.strip().split('\n') if l.strip()]
    if not lines:
        return {'observed_followed': False, 'confidence':'high', 'reason':'empty response', 'evidence_refs':[]}
    numbered = [l for l in lines if re.match(r'^\d+[\.\)]\s+', l)]
    is_numbered = len(numbered) >= 1 and len(numbered) == len(lines)
    # Check no concluding sentence: last line must be a numbered item (already ensured if is_numbered)
    last = lines[-1]
    last_is_item = bool(re.match(r'^\d+[\.\)]\s+', last))
    followed = (first_ok is True) and is_numbered and last_is_item
    reason = f'first_tool_ok={first_ok}, all_numbered={is_numbered}, last_is_item={last_is_item}'
    if first_ok is None:
        return {'observed_followed': None, 'confidence':'low', 'reason':'no tool calls observed; '+reason, 'evidence_refs':[]}
    return {'observed_followed': bool(followed), 'confidence':'high', 'reason': reason, 'evidence_refs':[]}
