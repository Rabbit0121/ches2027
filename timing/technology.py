"""Check native cell functions and rename physical pins to canonical gate aliases."""
import re
from itertools import permutations
from ..search.nldm import timing as b
from ..core.model import ARITY, gate
from ..core.structure import physical_pins

def truth(expression, inputs):
    """Liberty combinational expression evaluator, no Python eval."""
    tokens = re.findall("[A-Za-z_][A-Za-z_0-9]*|[01]|[!~\\'()&*|+^]", expression)
    if re.sub('\\s+', '', expression) != ''.join(tokens):
        raise ValueError('Unsupported function ' + expression)
    mask = (1 << (1 << len(inputs))) - 1
    vals = {p: sum(((x >> i & 1) << x for x in range(1 << len(inputs)))) for i, p in enumerate(inputs)}
    pos = 0

    def atom():
        nonlocal pos
        if pos >= len(tokens):
            raise ValueError('Incomplete function')
        t = tokens[pos]
        pos += 1
        if t in ('!', '~'):
            v = ~atom() & mask
        elif t == '(':
            v = disjunction()
            if pos >= len(tokens) or tokens[pos] != ')':
                raise ValueError('Unbalanced function')
            pos += 1
        elif t in vals:
            v = vals[t]
        elif t in ('0', '1'):
            v = mask if t == '1' else 0
        else:
            raise ValueError('Unknown function variable ' + t)
        while pos < len(tokens) and tokens[pos] == "'":
            v ^= mask
            pos += 1
        return v

    def conjunction():
        nonlocal pos
        v = atom()
        while pos < len(tokens):
            t = tokens[pos]
            if t in ('&', '*'):
                pos += 1
                v &= atom()
            elif t not in ('|', '+', '^', ')'):
                v &= atom()
            else:
                break
        return v

    def xor():
        nonlocal pos
        v = conjunction()
        while pos < len(tokens) and tokens[pos] == '^':
            pos += 1
            v ^= conjunction()
        return v

    def disjunction():
        nonlocal pos
        v = xor()
        while pos < len(tokens) and tokens[pos] in ('|', '+'):
            pos += 1
            v |= xor()
        return v
    v = disjunction()
    if pos != len(tokens):
        raise ValueError('Trailing function tokens')
    return v

def classify(body):
    if re.search('\\b(ff|latch|statetable)\\s*\\(|\\bthree_state\\s*:', body):
        return None
    pins = {p: pb for p, pb in b.groups(body, 'pin')}
    ins = sorted((p for p, pb in pins.items() if b.attr(pb, 'direction') == 'input'))
    outs = [p for p, pb in pins.items() if b.attr(pb, 'direction') == 'output']
    if len(outs) != 1 or not 1 <= len(ins) <= 4:
        return None
    fun = b.attr(pins[outs[0]], 'function')
    if not fun:
        return None
    for ordered in permutations(ins):
        val = truth(fun, ordered)
        literals = [sum(((x >> i & 1) << x for x in range(1 << len(ins)))) for i in range(len(ins))]
        for kind, arity in ARITY.items():
            if arity == len(ins) and gate(kind, literals, (1 << (1 << len(ins))) - 1) == val:
                return (kind, dict(zip(physical_pins(kind), ordered)), outs[0])
    return None

def rename_tokens(text, mapping):
    return re.sub('\\b[A-Za-z_][A-Za-z_0-9]*\\b', lambda m: mapping.get(m[0], m[0]), text)

def alias_cell(body, kind, strength=1):
    found = classify(body)
    if found is None or found[0] != kind:
        raise ValueError('Physical cell does not implement the requested gate')
    _, pinmap, output = found
    renamed = {v: k for k, v in pinmap.items()}
    renamed[output] = 'Z'
    return 'cell (' + kind + '_X' + str(strength) + ') {' + rename_tokens(body, renamed) + '}'
