def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    lower = text.lower()
    salutations = ['dear ', 'to the', 'to:', 'attention:', 'honorable', 'esteemed']
    has_salutation = any(lower.startswith(s) or ('\n'+s) in '\n'+lower[:200] for s in salutations)
    # Look at first non-empty line
    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), '')
    if not has_salutation:
        has_salutation = any(first_line.lower().startswith(s) for s in salutations)
    closings = ['sincerely', 'respectfully', 'regards', 'yours truly', 'faithfully', 'cordially']
    tail = text[-600:].lower()
    has_closing = any(c in tail for c in closings)
    # Signature block: look for name/title lines after closing
    sig_block = False
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if has_closing and len(lines) >= 2:
        # last few lines should contain a name or title indicator
        last_lines = ' \n'.join(lines[-5:]).lower()
        sig_indicators = ['advisor', 'attaché', 'attache', 'officer', 'analyst', 'secretary', 'ambassador', 'envoy', 'department', 'bureau', 'office of', 'signed,', 'minister']
        sig_block = any(ind in last_lines for ind in sig_indicators)
    followed = has_salutation and has_closing and sig_block
    return {
        'observed_followed': bool(followed),
        'confidence': 'high' if followed else 'medium',
        'reason': f'salutation={has_salutation}, closing={has_closing}, signature_block={sig_block}',
        'evidence_refs': []
    }
