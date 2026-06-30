def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    reasons = []
    words = response.split()
    wc = len(words)
    if wc > 40:
        reasons.append('word count ' + str(wc) + ' exceeds 40')
    articles = {'a', 'an', 'the'}
    found_articles = []
    for w in words:
        bare = re.sub(r'[^A-Za-z]', '', w).lower()
        if bare in articles:
            found_articles.append(w)
    if found_articles:
        reasons.append('contains articles: ' + ', '.join(found_articles[:5]))
    # Allowed punctuation: periods only. Find disallowed punctuation chars.
    disallowed = []
    for ch in response:
        if ch.isalnum() or ch.isspace() or ch == '.':
            continue
        disallowed.append(ch)
    if disallowed:
        uniq = sorted(set(disallowed))
        reasons.append('disallowed punctuation: ' + ''.join(uniq))
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'within 40 words, no articles, only periods as punctuation', 'evidence_refs': []}
