def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    low = text.lower()
    # Japanese fiscal year notation: FY2016, FY16, 平成28年度, 平成28, fiscal year 2016
    jfy_patterns = [r'fy\s*20\d{2}', r'fy\s*\d{2}\b', r'fiscal\s+year\s+20\d{2}', r'平成\s*\d+\s*年度?', r'令和\s*\d+\s*年度?']
    has_jfy = any(re.search(p, low) for p in jfy_patterns[:3]) or any(re.search(p, text) for p in jfy_patterns[3:])
    # JPY price: ¥, JPY, 円
    jpy_patterns = [r'¥\s*[\d,]+', r'jpy\s*[\d,]+', r'[\d,]+\s*jpy', r'[\d,]+\s*円', r'[\d,]+\s*yen']
    has_jpy = any(re.search(p, low) for p in jpy_patterns[:3] + [r'[\d,]+\s*yen']) or re.search(r'[\d,]+\s*円', text)
    followed = bool(has_jfy and has_jpy)
    return {'observed_followed': followed, 'confidence': 'high' if followed else 'medium', 'reason': f'jfy={bool(has_jfy)}, jpy={bool(has_jpy)}', 'evidence_refs': []}
