def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # detect any price mentions
    price_pattern = re.compile(r'(?:USD|US\$|\$|EUR|€|usd|eur)\s*\d|\d[\d,.]*\s*(?:USD|US\$|\$|EUR|€|usd|eur|dollars?|euros?)', re.IGNORECASE)
    has_price = bool(price_pattern.search(text))
    if not has_price:
        return {'observed_followed': None, 'confidence':'low','reason':'no price mentions detected','evidence_refs':[]}
    has_usd = bool(re.search(r'USD|US\$|\$\d|dollars?', text, re.IGNORECASE))
    has_eur = bool(re.search(r'EUR|€|euros?', text, re.IGNORECASE))
    # timestamp detection
    ts_pattern = re.compile(r'\b(20\d{2}-\d{2}-\d{2}|\d{4}/\d{2}/\d{2}|\d{2}:\d{2}(:\d{2})?|as of\s+[A-Za-z0-9, :\-/]+|timestamp[:\s])', re.IGNORECASE)
    has_ts = bool(ts_pattern.search(text))
    followed = has_usd and has_eur and has_ts
    reason = f'usd={has_usd}, eur={has_eur}, timestamp={has_ts}'
    return {'observed_followed': bool(followed), 'confidence':'medium','reason':reason,'evidence_refs':[]}
