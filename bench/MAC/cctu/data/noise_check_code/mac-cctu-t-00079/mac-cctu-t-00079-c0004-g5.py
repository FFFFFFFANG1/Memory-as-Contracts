def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    if not final.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    has_verified = '[VERIFIED]' in final
    tool_calls = trace.get('tool_calls') or []
    tool_names = [tc.get('name','') for tc in tool_calls if tc.get('name')]
    if not tool_names:
        enumerated = True
        missing = []
    else:
        missing = [n for n in tool_names if n and n not in final]
        enumerated = len(missing) == 0
    followed = has_verified and enumerated
    if has_verified:
        idx = final.find('[VERIFIED]')
        after = final[idx+len('[VERIFIED]'):].strip()
        if not after:
            followed = False
    reason = f'verified_present={has_verified}; missing_tool_mentions={missing}'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
