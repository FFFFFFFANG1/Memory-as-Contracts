import re
def evaluate(trace):
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty final response','evidence_refs':[]}
    binomial_re = re.compile(r'\(([A-Z][a-z]+(?:\s+[a-z]+){1,2})\)')
    binomials = binomial_re.findall(text)
    species_hints = ['salmon','tuna','cod','shark','whale','dolphin','seal','otter','crab','lobster','shrimp','oyster','mussel','clam','squid','octopus','jellyfish','coral','seaweed','kelp','seagrass','manatee','dugong','turtle','penguin','herring','mackerel','sardine','anchovy','sturgeon','eel','ray','skate','urchin','starfish','sea lion','walrus','barnacle','plankton','krill','sea otter','sea turtle']
    lower = text.lower()
    mentioned = [s for s in species_hints if re.search(r'\b'+re.escape(s)+r'\b', lower)]
    # Check each common species mention is followed (within ~80 chars) by a binomial parenthetical
    unpaired = []
    for s in mentioned:
        paired = False
        for m in re.finditer(r'\b'+re.escape(s)+r'\b', lower):
            window = text[m.end(): m.end()+120]
            if binomial_re.search(window):
                paired = True
                break
        if not paired:
            unpaired.append(s)
    if not mentioned and not binomials:
        return {'observed_followed': None,'confidence':'low','reason':'no obvious species mentions detected','evidence_refs':[]}
    if unpaired:
        return {'observed_followed': False,'confidence':'medium','reason':'species without binomial: '+', '.join(unpaired),'evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'mentioned species appear paired with binomials','evidence_refs':binomials}
