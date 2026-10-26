"""Correlate leftover bytes before the trailer with per-file feature counts."""
import os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw_probe as m

def trailer_len(t):
    # find the shortest suffix that is a valid trailer; return prefix (leftover) length
    for start in range(len(t)):
        s = t[start:]
        p = 0
        try:
            n = s[p]; p += 1 + 2 * n
            while s[p] != 0:
                if s[p] != 2: raise IndexError
                p += 3; p = s.index(0, p) + 1
            if p == len(s) - 1 and n >= 1:
                return start
        except (IndexError, ValueError):
            pass
    return None

d = sys.argv[1]
rows = []
for f in sorted(os.listdir(d)):
    buf = open(os.path.join(d, f), 'rb').read()
    try:
        w, h, g, t, st = m.parse(buf)
    except Exception:
        continue
    feats = collections.Counter()
    def walk(o, ctx):
        if not o or o == ('start',): return
        if o[0] == 'block':
            feats[f'{ctx}attr{o[1]:#x}'] += 1
        elif o[0] == 'level':
            feats[f'level_flag{o[1]}'] += 1; walk(o[3], 'lv'); walk(o[4], 'lv')
        elif o[0] == 'piston':
            feats[f'piston_s{o[1]}'] += 1; walk(o[2], 'pb')
        elif o[0] == 'head':
            feats['head'] += 1
    for row in g:
        for o in row:
            walk(o, '')
    rows.append((f, trailer_len(t), feats))

keys = sorted({k for _, _, fe in rows for k in fe})
# features whose presence best predicts leftover>0
for k in keys:
    a = sum(1 for _, L, fe in rows if fe[k] and L)
    b = sum(1 for _, L, fe in rows if fe[k] and not L)
    c = sum(1 for _, L, fe in rows if not fe[k] and L)
    if a + c and a / (a + b + c) > 0.3:
        print(f'{k:16} with&left={a:4} with&clean={b:4} without&left={c:4}')
print('leftover None:', sum(1 for _, L, _ in rows if L is None), ' >0:', sum(1 for _, L, _ in rows if L), ' 0:', sum(1 for _, L, _ in rows if L == 0))
# exact ratio test
for k in keys:
    ok = all((L or 0) == 3 * fe[k] for _, L, fe in rows if L is not None)
    if ok: print('EXACT 3*count', k)
