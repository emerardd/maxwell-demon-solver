"""Search which piston state values carry one extra trailing object."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mxw_inner import trailer_ok, files

def parse(buf, S):
    p = 0
    def rd():
        nonlocal p
        b = buf[p]; p += 1; return b
    def obj():
        nonlocal p
        tag = rd()
        if tag in (0, 1): return
        if tag == 2: rd(); rd(); return
        if tag == 3:
            rd(); p = buf.index(0, p) + 1; obj(); obj(); return
        if tag == 4:
            s = rd(); obj(); rd()
            if s in S: obj()
            return
        if tag == 5: rd(); rd(); rd(); return
        raise Exception(f'tag {tag}')
    w, h = rd(), rd()
    for _ in range(w * h): obj()
    return buf[p:]

best = []
for mask in range(256):
    S = {i for i in range(8) if mask >> i & 1}
    good = 0
    for buf in files:
        try:
            good += trailer_ok(parse(buf, S))
        except Exception:
            pass
    best.append((good, sorted(S)))
best.sort(reverse=True)
print(len(files), best[:6])
