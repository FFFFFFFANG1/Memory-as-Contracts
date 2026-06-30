def evaluate(trace):
    import re
    trajectory = trace.get('trajectory') or []
    assistant_msgs = []
    for step in trajectory:
        role = step.get('role') if isinstance(step, dict) else None
        if role and role != 'assistant':
            continue
        content = step.get('content') if isinstance(step, dict) else None
        if isinstance(content, str) and content.strip():
            assistant_msgs.append(content)
    final = trace.get('final_response')
    if isinstance(final, str) and final.strip() and (not assistant_msgs or assistant_msgs[-1] != final):
        assistant_msgs.append(final)
    if not assistant_msgs:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No assistant messages found', 'evidence_refs': []}
    bad_prefix = []
    for i, m in enumerate(assistant_msgs):
        if not m.lstrip().startswith('[ECON-PROFILE]'):
            bad_prefix.append(i)
    # Check monetary figures: look for non-USD currency symbols/codes
    non_usd_pattern = re.compile(r'(€|£|¥|₹|₽|₩|R\$|C\$|A\$|HK\$|S\$|NZ\$|\b(EUR|GBP|JPY|CNY|RMB|INR|RUB|KRW|CAD|AUD|CHF|MXN|BRL|ZAR|HKD|SGD|NZD|SEK|NOK|DKK|TRY)\b)', re.IGNORECASE)
    non_usd_hits = []
    for i, m in enumerate(assistant_msgs):
        if non_usd_pattern.search(m):
            non_usd_hits.append(i)
    if bad_prefix or non_usd_hits:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'bad_prefix_msgs={bad_prefix}, non_usd_msgs={non_usd_hits}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'All assistant messages prefixed correctly and no non-USD currency markers found', 'evidence_refs': []}
