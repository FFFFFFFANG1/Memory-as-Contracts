def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    names = [c.get('name') for c in calls]
    if not names:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls observed', 'evidence_refs': []}
    non_allowed = [n for n in names if n != 'gym_membership_pricing_tool']
    if non_allowed:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'other tools invoked: {sorted(set(non_allowed))}', 'evidence_refs': [{'type':'tool_calls','names':names}]}
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response, cannot check ranked numeric list', 'evidence_refs': []}
    # Look for a list of numeric prices
    nums = []
    list_like = False
    for line in resp.splitlines():
        s = line.strip()
        if re.match(r'^\s*(\d+[\.\)]|[-*•])\s', s) or re.match(r'^\s*\d+[\.\)]', s):
            list_like = True
        m = re.findall(r'\$?\s*\d+(?:[\.,]\d+)?', s)
        if m and (list_like or re.match(r'^\s*(\d+[\.\)]|[-*•])', s)):
            try:
                nums.append(float(re.sub(r'[^0-9\.]', '', m[0])))
            except Exception:
                pass
    if len(nums) < 2:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'could not detect ranked numeric list of prices', 'evidence_refs': [{'response_excerpt': resp[:200]}]}
    ranked = nums == sorted(nums) or nums == sorted(nums, reverse=True)
    if not ranked:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'numeric list not ranked: {nums}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'only gym_membership_pricing_tool used and prices ranked: {nums}', 'evidence_refs': [{'numbers': nums}]}
