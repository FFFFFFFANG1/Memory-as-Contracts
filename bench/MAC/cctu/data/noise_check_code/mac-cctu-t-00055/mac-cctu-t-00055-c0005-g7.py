def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    # Group by tool name in order, detect 3 consecutive failures
    def is_fail(c):
        r = c.get('result')
        if r is None:
            return False
        s = str(r).lower()
        return ('error' in s) or ('failed' in s) or ('failure' in s) or ('exception' in s)
    streaks = {}
    triggered = []
    last_tool = None
    streak = 0
    for c in calls:
        name = c.get('name') or c.get('tool') or ''
        if name != last_tool:
            streak = 0
            last_tool = name
        if is_fail(c):
            streak += 1
            if streak == 3:
                triggered.append(name)
        else:
            streak = 0
    if not triggered:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool failed three consecutive times; constraint not triggered.', 'evidence_refs': []}
    low = final.lower()
    has_appendix = bool(re.search(r'(failure[- ]?log|failure appendix|appendix.*failure|error log)', low))
    mentions_errors = ('error' in low) or ('failed' in low)
    mentions_adjust = ('adjust' in low) or ('parameter' in low) or ('retry' in low) or ('modified' in low)
    followed = has_appendix and mentions_errors and mentions_adjust
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': f'Triggered tools={triggered}; appendix={has_appendix}, errors={mentions_errors}, adjustments={mentions_adjust}.', 'evidence_refs': []}
