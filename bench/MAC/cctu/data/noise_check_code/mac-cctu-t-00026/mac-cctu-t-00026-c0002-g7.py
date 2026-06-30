def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    low = text.lower()
    # Detect table: markdown pipe table or HTML table
    pipe_lines = [l for l in text.splitlines() if l.count('|') >= 2]
    has_table = len(pipe_lines) >= 3 or '<table' in low
    mentions_precinct = 'precinct' in low
    # Detect 0.5% threshold and escalation/flag language
    has_threshold = bool(re.search(r'0\.5\s*%|0\.5\s*percent', low))
    has_flag = any(k in low for k in ['flag','escalat','manual review','discrepan'])
    passed = has_table and mentions_precinct and has_threshold and has_flag
    reason = f'table={has_table}, precinct={mentions_precinct}, threshold0.5={has_threshold}, flag/escalate={has_flag}'
    return {'observed_followed': bool(passed), 'confidence':'medium' if passed else 'low', 'reason': reason, 'evidence_refs': []}
