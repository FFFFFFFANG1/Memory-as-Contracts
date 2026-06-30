def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    words = len(resp.split())
    within = words <= 350
    lines = resp.splitlines()
    bar_chars = set('#|*=█▇▆▅▄▃▂▁-')
    bar_lines = 0
    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            continue
        # line looks like 'label ####' or contains run of bar chars
        m = re.search(r'([#|*=█▇▆▅▄▃▂▁\-]{3,})', stripped)
        if m:
            bar_lines += 1
    has_chart = bar_lines >= 2
    mentions_throughput = bool(re.search(r'throughput|tonnage|port', resp, re.I))
    followed = within and has_chart
    return {
        'observed_followed': bool(followed),
        'confidence': 'high' if (has_chart or not within) else 'medium',
        'reason': f'words={words} bar_lines={bar_lines} within350={within} mentionsThroughput={mentions_throughput}',
        'evidence_refs': []
    }
