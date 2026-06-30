def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    # Split into trailing blocks
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    if len(paragraphs) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'need a confidence sentence followed by a commentary paragraph', 'evidence_refs': []}
    commentary = paragraphs[-1]
    prior = paragraphs[-2]
    # Find a numeric confidence sentence somewhere near the end of prior block (or its last sentence)
    sentences = re.split(r'(?<=[.!?])\s+', prior)
    conf_sent = None
    for s in reversed(sentences):
        if re.search(r'confidence', s, re.IGNORECASE) and re.search(r'\d', s):
            conf_sent = s
            break
    if conf_sent is None:
        # also allow confidence sentence to be the last sentence of the entire text before commentary
        joined = prior
        if re.search(r'confidence', joined, re.IGNORECASE) and re.search(r'\d', joined):
            conf_sent = joined
    if conf_sent is None:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no numeric confidence score sentence found before commentary paragraph', 'evidence_refs': []}
    if len(commentary) < 400:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'commentary paragraph is {len(commentary)} chars, under 400', 'evidence_refs': []}
    macro_terms = ['macro','demand','supply','opec','inflation','geopolit','growth','recession','dollar','fed','interest rate','china','sanction','stimulus','gdp','currency']
    if not any(t in commentary.lower() for t in macro_terms):
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'commentary paragraph does not appear to discuss macro drivers', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'confidence sentence with numeric score followed by >=400 char macro commentary', 'evidence_refs': []}
