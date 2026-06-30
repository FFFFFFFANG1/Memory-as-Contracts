def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty response', 'evidence_refs': []}
    lines = [ln.rstrip() for ln in response.splitlines()]
    non_empty = [ln for ln in lines if ln.strip()]
    if not non_empty:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no content lines', 'evidence_refs': []}
    numbered_re = re.compile(r'^\s*(\d+)[\.\)]\s+\S')
    bullet_re = re.compile(r'^\s*[-*+]\s+\S')
    numbered_lines = [ln for ln in non_empty if numbered_re.match(ln)]
    bullet_lines = [ln for ln in non_empty if bullet_re.match(ln)]
    if len(numbered_lines) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'fewer than 2 numbered hop items found', 'evidence_refs': []}
    nums = []
    for ln in numbered_lines:
        m = numbered_re.match(ln)
        if m:
            nums.append(int(m.group(1)))
    expected = list(range(nums[0], nums[0] + len(nums)))
    if nums != expected:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'numbering not sequential: ' + str(nums), 'evidence_refs': []}
    # Each hop should be a single bullet/line, not multi-paragraph synthesis
    # Detect final synthesized answer: lines after the last numbered item that look like prose conclusion
    last_idx = None
    for i, ln in enumerate(non_empty):
        if numbered_re.match(ln):
            last_idx = i
    trailing = non_empty[last_idx+1:] if last_idx is not None else []
    # Allow short continuation if it's clearly part of the last hop (indented), else flag
    synth_markers = re.compile(r'(?i)\b(answer|therefore|thus|in conclusion|final answer|the answer is|so,|hence)\b')
    for ln in trailing:
        if synth_markers.search(ln):
            return {'observed_followed': False, 'confidence': 'high', 'reason': 'final synthesized answer present after hop list: ' + ln.strip()[:80], 'evidence_refs': []}
    # Also check inside the response body for explicit 'Final answer:' style lines
    for ln in non_empty:
        if re.match(r'(?i)^\s*(final answer|answer)\s*[:\-]', ln):
            return {'observed_followed': False, 'confidence': 'high', 'reason': 'explicit final answer label present', 'evidence_refs': []}
    # Check non-numbered, non-bullet prose lines that are not trailing whitespace
    extraneous = []
    for ln in non_empty:
        if numbered_re.match(ln) or bullet_re.match(ln):
            continue
        # allow a short header line at top
        if ln is non_empty[0] and len(ln.split()) <= 10:
            continue
        extraneous.append(ln)
    if len(extraneous) > 1:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'extraneous prose lines suggest synthesized content: ' + str(extraneous[:2]), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'numbered hop list with sequential numbering and no synthesized final answer', 'evidence_refs': []}
