def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    words = len(re.findall(r'\S+', text))
    headers = re.findall(r'(?m)^#{1,6}\s+\S', text)
    has_multi_section = len(headers) >= 2
    has_markdown = bool(headers) or bool(re.search(r'\*\*|__|\* |- |\|', text))
    has_chart = bool(re.search(r'!\[[^\]]*\]\([^)]+\)|```chart|```mermaid|<img|chart:|\bfigure\b', text, re.I))
    low = text.lower()
    has_vol = ('volatility' in low) and ('month' in low)
    has_opec = 'opec' in low
    checks = {'markdown': has_markdown, 'multi_section': has_multi_section, 'words>=800': words >= 800, 'embedded_chart': has_chart, 'mom_volatility': has_vol, 'opec_commentary': has_opec}
    failed = [k for k,v in checks.items() if not v]
    followed = len(failed) == 0
    return {'observed_followed': followed, 'confidence': 'high' if followed or len(failed) >= 2 else 'medium', 'reason': 'checks: ' + str(checks), 'evidence_refs': []}
