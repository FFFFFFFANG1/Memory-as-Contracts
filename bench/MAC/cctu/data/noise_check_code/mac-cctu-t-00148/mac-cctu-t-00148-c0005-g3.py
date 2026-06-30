def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    words = re.findall(r"\S+", resp)
    wc = len(words)
    under_limit = wc < 80
    has_pipe_table = bool(re.search(r'^\s*\|.*\|\s*$', resp, re.MULTILINE))
    has_table_sep = bool(re.search(r'^\s*\|?\s*:?-{3,}', resp, re.MULTILINE))
    has_html_table = bool(re.search(r'<table[\s>]', resp, re.IGNORECASE))
    has_tab_cols = False
    for line in resp.splitlines():
        if line.count('\t') >= 2:
            has_tab_cols = True
            break
    tabular = has_pipe_table or has_table_sep or has_html_table or has_tab_cols
    followed = under_limit and not tabular
    reason = f'word_count={wc}, under_80={under_limit}, tabular_detected={tabular}'
    return {'observed_followed': bool(followed), 'confidence': 'high', 'reason': reason, 'evidence_refs': []}
