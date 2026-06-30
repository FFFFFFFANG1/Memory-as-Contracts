def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    # Check first tool call is historical_leadership_finder
    first = calls[0].get('name')
    if first != 'historical_leadership_finder':
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'First tool call was {first}, not historical_leadership_finder', 'evidence_refs': [{'first_tool': first}]}
    # Check final answer is a Markdown table
    lines = [l for l in final.splitlines() if l.strip()]
    table_lines = [l for l in lines if l.strip().startswith('|') and l.strip().endswith('|')]
    has_sep = any(re.match(r'^\s*\|[\s\-:|]+\|\s*$', l) for l in table_lines)
    if len(table_lines) < 2 or not has_sep:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Final answer is not a Markdown table', 'evidence_refs': [{'final_snippet': final[:200]}]}
    low = final.lower()
    mentions_minister = 'minister' in low
    mentions_tenure = any(k in low for k in ['tenure', 'term', 'period', 'years', 'served', 'from', 'in office'])
    if not (mentions_minister and mentions_tenure):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Markdown table does not summarize minister and tenure', 'evidence_refs': [{'final_snippet': final[:300]}]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'First tool was historical_leadership_finder and final answer is a Markdown table with minister and tenure', 'evidence_refs': [{'first_tool': first, 'table_lines': len(table_lines)}]}
