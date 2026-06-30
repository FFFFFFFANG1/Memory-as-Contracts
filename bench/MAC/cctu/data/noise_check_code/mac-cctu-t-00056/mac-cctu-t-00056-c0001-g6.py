def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    low = response.lower()
    producers = re.findall(r'<producer\b[^>]*>', response, re.IGNORECASE)
    if not producers:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no <producer> elements found', 'evidence_refs': []}
    has_xml_struct = bool(re.search(r'</producer\s*>', response, re.IGNORECASE)) or bool(re.search(r'<producer[^>]*/>', response, re.IGNORECASE))
    if not has_xml_struct:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '<producer> elements not properly closed as XML', 'evidence_refs': []}
    # Check summary lines for no concluding punctuation
    bad_endings = ('.', '!', '?', ';', ':', ',')
    offenders = []
    for raw in response.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('<') and line.endswith('>'):
            continue
        # Extract inner text if line is like <tag>text</tag>
        inner_match = re.match(r'^<[^>]+>(.*?)</[^>]+>$', line)
        if inner_match:
            text = inner_match.group(1).strip()
        elif '<' in line or '>' in line:
            continue
        else:
            text = line
        if not text:
            continue
        if text.endswith(bad_endings):
            offenders.append(text[:80])
    if offenders:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'summary line(s) ended with punctuation: ' + ' | '.join(offenders[:3]), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'XML <producer> elements present and summary lines lack concluding punctuation', 'evidence_refs': []}
