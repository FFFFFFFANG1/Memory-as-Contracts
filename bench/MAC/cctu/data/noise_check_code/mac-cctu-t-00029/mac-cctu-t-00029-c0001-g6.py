def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    tool_calls = trace.get('tool_calls') or []
    # Look at tail of response for a numbered list
    lines = response.rstrip().splitlines()
    # Find trailing numbered list lines
    numbered_pattern = re.compile(r'^\s*(\d+)[\.\)]\s+\S')
    trailing = []
    for line in reversed(lines):
        if not line.strip():
            if trailing:
                break
            continue
        if numbered_pattern.match(line):
            trailing.append(line)
        else:
            break
    trailing.reverse()
    if len(trailing) < 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no numbered list found at end of response', 'evidence_refs': []}
    # Verify numbering starts at 1 and is sequential
    nums = []
    for l in trailing:
        m = numbered_pattern.match(l)
        if m:
            nums.append(int(m.group(1)))
    if not nums or nums[0] != 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'numbered list does not start at 1', 'evidence_refs': []}
    for i, n in enumerate(nums):
        if n != i + 1:
            return {'observed_followed': False, 'confidence': 'high', 'reason': 'numbered list not sequential', 'evidence_refs': []}
    # If tool calls exist, list length should reasonably reflect them
    if tool_calls:
        if len(trailing) < len(tool_calls):
            return {'observed_followed': False, 'confidence': 'medium', 'reason': 'numbered list shorter than number of tool invocations', 'evidence_refs': []}
        # Check that tool names appear somewhere in the listed items
        tool_names = [str(tc.get('name') or '') for tc in tool_calls]
        listed_text = '\n'.join(trailing).lower()
        missing = [t for t in tool_names if t and t.lower() not in listed_text]
        if missing:
            return {'observed_followed': False, 'confidence': 'medium', 'reason': 'tool names missing from numbered list: ' + ', '.join(missing), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'numbered list of tool invocations present at end', 'evidence_refs': []}
