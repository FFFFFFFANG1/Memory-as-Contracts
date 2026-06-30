def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    parts = re.split(r'(?<=[.!?])\s+', text.rstrip())
    closing = (parts[-1] if parts else text).strip()
    if not closing:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no closing sentence', 'evidence_refs': []}
    if re.search(r'\d', closing):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'closing sentence contains digit characters: ' + closing, 'evidence_refs': []}
    number_words = ['zero','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve','thirteen','fourteen','fifteen','sixteen','seventeen','eighteen','nineteen','twenty','thirty','forty','fifty','sixty','seventy','eighty','ninety','hundred','thousand','million','billion','trillion']
    low = closing.lower()
    found = [w for w in number_words if re.search(r'\b' + w + r'\b', low)]
    if len(found) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'closing sentence does not spell out two numerical quantities; matches=' + str(found), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'closing sentence has no digits and contains number words: ' + str(found), 'evidence_refs': []}
