def evaluate(trace):
    import re
    calls = trace.get('tool_calls', []) or []
    final = (trace.get('final_response') or '')
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls to assess cross-checking.', 'evidence_refs': []}
    def has_number(x):
        try:
            s = str(x)
        except Exception:
            return False
        return bool(re.search(r'\d', s))
    numeric_calls = [c for c in calls if has_number(c.get('result'))]
    tools_used = [c.get('name') for c in calls if c.get('name')]
    distinct_tools = set(tools_used)
    if not numeric_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No numeric values retrieved from tools.', 'evidence_refs': []}
    if len(distinct_tools) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Only one tool used; no independent cross-check possible.', 'evidence_refs': [str(sorted(distinct_tools))]}
    text = final.lower()
    cues = ['cross-check', 'cross check', 'verified', 'verify', 'corroborat', 'second source', 'independent', 'discrepan', 'agreement', 'disagree', 'within 5', 'within five', '5%', 'flag']
    mentions = [w for w in cues if w in text]
    # need evidence that the SAME numeric value was checked by a second tool
    # heuristic: count tools per numeric-looking quantity is hard; rely on multi-tool + textual cues
    if mentions:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'Multiple tools used and response mentions cross-check/verification cues: ' + ', '.join(mentions), 'evidence_refs': []}
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'Multiple tools used but no explicit cross-check or 5% disagreement check observed in response.', 'evidence_refs': []}
