def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '').strip()
    tool_calls = trace.get('tool_calls') or []
    if not response:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty final response', 'evidence_refs': []}
    reasons = []
    markdown_patterns = [r'\*\*', r'__', r'`', r'^#{1,6}\s', r'^\s*[-*+]\s', r'^\s*\d+\.\s', r'\[[^\]]+\]\([^)]+\)', r'!\[']
    for pat in markdown_patterns:
        if re.search(pat, response, re.MULTILINE):
            reasons.append('markdown formatting detected: ' + pat)
            break
    if '\n' in response.strip():
        reasons.append('response spans multiple lines, not a single sentence')
    # Count sentence terminators
    core = response.rstrip()
    # Strip a single trailing terminator before counting
    inner = core[:-1] if core and core[-1] in '.!?' else core
    terminators = re.findall(r'[.!?](?=\s|$)', inner)
    if len(terminators) > 0:
        reasons.append('multiple sentences detected')
    decorative_patterns = [r'(?i)\bhope this helps\b', r'(?i)\blet me know if\b', r'(?i)\bfeel free to\b', r'(?i)\bif you have any\b', r'(?i)\bhappy to help\b', r'(?i)\bplease let me know\b', r'(?i)\bI hope\b']
    for pat in decorative_patterns:
        if re.search(pat, response):
            reasons.append('decorative trailing phrase detected')
            break
    if not tool_calls:
        # Constraint references tool call usage; with no observable tool activity we cannot confirm interaction behavior
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no tool calls observed; cannot confirm interaction constraint context', 'evidence_refs': []}
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'single plain-text sentence without markdown or decorative trailing phrases', 'evidence_refs': []}
