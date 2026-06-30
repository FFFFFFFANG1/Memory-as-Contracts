import re

def evaluate(trace):
    trace = trace or {}
    final = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': []}
    failures = []
    evidence = []
    # Identify executive summary section
    summary_text = final
    m = re.search(r'(?is)executive\s+summary\s*[:\-\n]+(.*?)(?:\n\s*\n[A-Z][^\n]{0,80}\n|\Z)', final)
    if m:
        summary_text = m.group(1).strip()
        evidence.append({'section': 'executive_summary_extracted', 'chars': len(summary_text)})
    else:
        # Fallback: first paragraph block
        parts = re.split(r'\n\s*\n', final.strip(), maxsplit=1)
        summary_text = parts[0]
        evidence.append({'section': 'first_block_fallback', 'chars': len(summary_text)})
    words = re.findall(r'\S+', summary_text)
    wc = len(words)
    evidence.append({'summary_word_count': wc})
    if wc > 200:
        failures.append(f'executive summary {wc} words exceeds 200')
    # Lead with headline temperature anomaly figure
    lead = summary_text.lstrip()
    # Take first sentence/line
    first_chunk = re.split(r'(?<=[.!?])\s|\n', lead, maxsplit=1)[0] if lead else ''
    evidence.append({'lead': first_chunk[:200]})
    has_anomaly_term = bool(re.search(r'(?i)anomaly|anomalies', first_chunk))
    has_number = bool(re.search(r'[+\-]?\d+(?:\.\d+)?\s*(?:°|deg|\u00b0)?\s*(?:C|F|K|celsius|fahrenheit)?', first_chunk))
    has_temp_unit = bool(re.search(r'(?i)°|\u00b0|deg\s*c|deg\s*f|celsius|fahrenheit|\bK\b|temperature', first_chunk))
    if not has_anomaly_term:
        failures.append('lead does not mention temperature anomaly')
    if not has_number:
        failures.append('lead lacks a numeric figure')
    if not has_temp_unit and not has_anomaly_term:
        failures.append('lead lacks temperature indicator')
    # Tool must have been used
    used = [c for c in tool_calls if str(c.get('name') or '') == 'weather_data_retriever']
    evidence.append({'weather_data_retriever_calls': len(used)})
    if not used:
        failures.append('weather_data_retriever was not called')
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:6]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'executive summary <=200 words, leads with temp anomaly figure, weather tool used', 'evidence_refs': evidence}
