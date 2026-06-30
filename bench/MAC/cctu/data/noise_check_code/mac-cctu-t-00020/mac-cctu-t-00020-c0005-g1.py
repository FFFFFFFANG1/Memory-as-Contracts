def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    analyzer_calls = [tc for tc in tool_calls if (tc.get('name') or '') == 'election_result_analyzer']
    if not analyzer_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'election_result_analyzer was never called', 'evidence_refs': []}
    # Check table presence in final response
    has_md_table = '|' in final and re.search(r'\|.*\|', final) is not None and final.count('|') >= 4
    has_separator = bool(re.search(r'\|\s*[-:]+\s*\|', final))
    has_html_table = '<table' in final.lower()
    tabulated = (has_md_table and has_separator) or has_html_table
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to inspect', 'evidence_refs': []}
    if not tabulated:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Final response lacks a tabulated breakdown of vote shares', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'election_result_analyzer was called and final response contains a table', 'evidence_refs': []}
