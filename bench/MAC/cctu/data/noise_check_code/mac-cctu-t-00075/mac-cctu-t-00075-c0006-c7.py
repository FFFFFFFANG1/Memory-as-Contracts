def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty', 'evidence_refs': []}
    last = lines[-1].strip()
    # detect list markers in last line
    if re.match(r'^(\s*[-*+\u2022]|\s*\d+[\.\)])', last):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'final line is a list item', 'evidence_refs': [last]}
    # final line should be a single sentence
    # count sentence terminators
    sentences = re.split(r'(?<=[.!?])\s+', last)
    sentences = [s for s in sentences if s.strip()]
    if len(sentences) != 1:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'final summary has {len(sentences)} sentences', 'evidence_refs': [last]}
    # check for enumeration patterns: commas with 'and', semicolons, or 'first/second'
    if ';' in last or re.search(r'\b(first|second|third|1\)|2\))', last, re.I):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'enumeration-like structure in summary', 'evidence_refs': [last]}
    # heuristic: must mention some state name (US state list partial) and look like a sentence
    states = ['Alabama','Alaska','Arizona','Arkansas','California','Colorado','Connecticut','Delaware','Florida','Georgia','Hawaii','Idaho','Illinois','Indiana','Iowa','Kansas','Kentucky','Louisiana','Maine','Maryland','Massachusetts','Michigan','Minnesota','Mississippi','Missouri','Montana','Nebraska','Nevada','New Hampshire','New Jersey','New Mexico','New York','North Carolina','North Dakota','Ohio','Oklahoma','Oregon','Pennsylvania','Rhode Island','South Carolina','South Dakota','Tennessee','Texas','Utah','Vermont','Virginia','Washington','West Virginia','Wisconsin','Wyoming']
    has_state = any(s in last for s in states)
    if not has_state:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no recognizable US state in final sentence', 'evidence_refs': [last]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'final line is a single prose sentence naming a state', 'evidence_refs': [last]}
