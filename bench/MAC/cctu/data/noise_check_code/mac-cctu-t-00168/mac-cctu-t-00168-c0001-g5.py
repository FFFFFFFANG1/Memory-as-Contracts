def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    # Find groups of two or more numbers that appear to be compared (separated by some delimiter)
    # Look for patterns like 'N <delim> N' where delim is not a pipe
    num = r'-?\d+(?:[.,]\d+)?'
    # Find any sequence of >=2 numbers separated by short non-alphanumeric delimiters
    pattern = re.compile(rf'({num})(\s*[^\w\s|]\s*)({num})')
    bad = []
    for m in pattern.finditer(resp):
        delim = m.group(2).strip()
        # ignore arithmetic/range typical separators that aren't comparison composites? Keep strict: any non-pipe delimiter between two numbers is suspect
        if delim and '|' not in delim:
            bad.append(m.group(0))
    # Check if any pipe-delimited numerical composite exists
    pipe_pattern = re.compile(rf'{num}\s*\|\s*{num}')
    has_pipe_composite = bool(pipe_pattern.search(resp))
    # Determine if response even contains a composite comparison
    multi_num = re.findall(num, resp)
    if len(multi_num) < 2:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no composite numerical comparison found', 'evidence_refs': []}
    if bad and not has_pipe_composite:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'numerical values separated by non-pipe delimiter: {bad[:3]}', 'evidence_refs': bad[:3]}
    if has_pipe_composite and not bad:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'pipe used between numerical comparison values', 'evidence_refs': [m.group(0) for m in pipe_pattern.finditer(resp)][:3]}
    if has_pipe_composite and bad:
        return {'observed_followed': False, 'confidence': 'low', 'reason': f'mixed delimiters; non-pipe found: {bad[:3]}', 'evidence_refs': bad[:3]}
    return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no clear composite numerical comparison detected', 'evidence_refs': []}
