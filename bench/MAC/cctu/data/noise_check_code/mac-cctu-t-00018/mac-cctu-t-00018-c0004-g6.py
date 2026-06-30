def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    lines = [ln for ln in response.splitlines() if ln.strip() != '']
    if len(lines) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'expected two-line block', 'evidence_refs': []}
    if len(lines) > 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'more than two non-empty lines', 'evidence_refs': []}
    first, second = lines[0].strip(), lines[1].strip()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', first):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'first line not YYYY-MM-DD', 'evidence_refs': []}
    try:
        import datetime
        datetime.date.fromisoformat(first)
    except Exception:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'first line not a valid date', 'evidence_refs': []}
    if not second:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'second line empty', 'evidence_refs': []}
    if second[-1] in '.!?;,:':
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'second line ends with trailing punctuation', 'evidence_refs': []}
    # one-sentence heuristic: no internal sentence terminators followed by space+capital
    if re.search(r'[.!?]\s+\S', second):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'second line appears to contain multiple sentences', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'two-line block with ISO date and unpunctuated single sentence', 'evidence_refs': []}
