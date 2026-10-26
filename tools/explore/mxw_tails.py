import os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw_probe as m

d = sys.argv[1]
c = collections.Counter(); ex = collections.defaultdict(list)
for f in sorted(os.listdir(d)):
    if not f.endswith('.mxw'):
        continue
    buf = open(os.path.join(d, f), 'rb').read()
    try:
        w, h, g, t, st = m.parse(buf)
    except Exception as e:
        print('FAIL', f, e, buf.hex(' '))
        continue
    starts = [(x, y) for y, row in enumerate(g) for x, o in enumerate(row) if o == ('start',)]
    c[len(t)] += 1
    ex[len(t)].append((f, f'{w}x{h}', 'starts', starts, t.hex(' ')))
for k in sorted(ex):
    print(k, c[k])
    for e in ex[k][:3]:
        print('   ', e)
