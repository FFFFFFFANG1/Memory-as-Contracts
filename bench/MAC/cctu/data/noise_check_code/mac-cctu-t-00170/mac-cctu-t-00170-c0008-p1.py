def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    # Check for table markers
    has_table = bool(re.search(r'\|.*\|', text)) or bool(re.search(r'^\s*\|', text, re.MULTILINE)) or '---|' in text
    # Check for 'Step X:' labels
    has_step_labels = bool(re.search(r'\bStep\s*\d+\s*:', text, re.IGNORECASE))
    # Check single sentence: count sentence terminators not at end
    stripped = text.rstrip()
    # Remove trailing terminator
    body = re.sub(r'[.!?]+\s*$', '', stripped)
    # Count sentence-ending punctuation in body (excluding decimals like 3.14)
    # Find . ! ? followed by space+capital or end
    sentence_breaks = re.findall(r'[.!?]+\s+(?=[A-Z])', body)
    # Also count newlines as potential sentence separators
    multi_line = '\n' in stripped.strip()
    issues = []
    if has_table:
        issues.append('contains table formatting')
    if has_step_labels:
        issues.append("contains 'Step X:' labels")
    if len(sentence_breaks) > 0:
        issues.append('appears to contain multiple sentences')
    if multi_line:
        issues.append('spans multiple lines')
    followed = len(issues) == 0
    return {
        'observed_followed': followed,
        'confidence': 'high' if (has_table or has_step_labels) else 'medium',
        'reason': 'Plain single-sentence prose' if followed else '; '.join(issues),
        'evidence_refs': []
    }
