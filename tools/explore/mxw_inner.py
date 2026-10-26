"""Test: which piston property byte bit means 'contains an object'. Score = files whose trailer parses cleanly."""
import os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw_probe as m

def trailer_ok(t):
    p = 0
    try:
        n = t[p]; p += 1 + 2 * n
        while t[p] != 0:
            if t[p] != 2:
                return False
            p += 3
            p = t.index(0, p) + 1
        return p == len(t) - 1
    except (IndexError, ValueError):
        return False

d = sys.argv[1]
files = [open(os.path.join(d, f), 'rb').read() for f in sorted(os.listdir(d)) if f.endswith('.mxw')]

def run(pred):
    orig = m.parse
    good = 0
    for buf in files:
        # monkeypatch: re-implement piston read via predicate on (state, side)
        try:
            w, h, g, t, st = parse(buf, pred)
            good += trailer_ok(t)
        except Exception:
            pass
    return good

def parse(buf, pred):
    p = 0
    def rd():
        nonlocal p
        b = buf[p]; p += 1; return b
    def obj():
        nonlocal p
        tag = rd()
        if tag in (0, 1): return tag
        if tag == 2: rd(); rd(); return tag
        if tag == 3:
            rd(); p = buf.index(0, p) + 1; obj(); obj(); return tag
        if tag == 4:
            s = rd(); obj(); x = rd(); obj()
            if pred(s, x): obj()
            return tag
        if tag == 5: rd(); rd(); rd(); return tag
        if tag == 7: raise Exception('tag7')
        raise Exception(f'tag {tag}')
    w, h = rd(), rd()
    for _ in range(w * h): obj()
    return w, h, None, buf[p:], None

print('none', run(lambda s, x: False))
for bit in range(8):
    print('side bit', bit, run(lambda s, x, b=bit: (x >> b) & 1))
    print('state bit', bit, run(lambda s, x, b=bit: (s >> b) & 1))
print('side!=0', run(lambda s, x: x != 0))
