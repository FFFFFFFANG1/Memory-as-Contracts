def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Find currency-like price mentions
    # Patterns: currency symbol or code followed by number, or number followed by currency code
    price_pattern = re.compile(r'(?:[$€£¥₹]|\b(?:USD|EUR|GBP|JPY|CNY|INR|AUD|CAD|CHF|HKD|SGD|KRW|MXN|BRL|RUB|ZAR)\b)\s*-?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s*(?:USD|EUR|GBP|JPY|CNY|INR|AUD|CAD|CHF|HKD|SGD|KRW|MXN|BRL|RUB|ZAR)\b', re.IGNORECASE)
    matches = list(price_pattern.finditer(text))
    if not matches:
        return {'observed_followed': None,'confidence':'low','reason':'no forecasted price found','evidence_refs':[]}
    issues = []
    oks = []
    for m in matches:
        s = m.group(0)
        # Extract numeric portion
        num_match = re.search(r'-?\d[\d,]*(?:\.\d+)?', s)
        if not num_match:
            continue
        num_str = num_match.group(0).replace(',', '')
        is_integer = '.' not in num_str
        # Look ahead up to 80 chars for parenthetical interval
        tail = text[m.end():m.end()+120]
        has_paren = bool(re.search(r'^\s*\(', tail)) or bool(re.search(r'\([^)]*(?:\d|confidence|CI|interval|±)[^)]*\)', tail, re.IGNORECASE))
        if not is_integer:
            issues.append(f'price {s} not integer')
        if not has_paren:
            issues.append(f'price {s} missing parenthetical CI')
        if is_integer and has_paren:
            oks.append(s)
    if issues:
        return {'observed_followed': False,'confidence':'medium','reason':'; '.join(issues[:3]),'evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':f'{len(oks)} price(s) formatted with integer and CI','evidence_refs':[]}
