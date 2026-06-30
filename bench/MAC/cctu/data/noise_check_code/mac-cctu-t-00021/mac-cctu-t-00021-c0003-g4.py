def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    words = re.findall(r"\S+", text)
    wc = len(words)
    has_pipe_table = bool(re.search(r'^\s*\|.*\|\s*$', text, re.MULTILINE)) and bool(re.search(r'^\s*\|?\s*:?-{3,}', text, re.MULTILINE))
    has_html_table = bool(re.search(r'<table[\s>]', text, re.IGNORECASE))
    tabular = has_pipe_table or has_html_table
    under_limit = wc < 80
    followed = under_limit and not tabular
    reason = f'word_count={wc}, tabular={tabular}'
    return {'observed_followed': bool(followed), 'confidence':'high','reason':reason,'evidence_refs':[]}
