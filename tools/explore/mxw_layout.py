"""Print a level's cells one per token, row by row, to eyeball the encoding."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw_probe as m

buf = open(sys.argv[1], 'rb').read()
w, h, g, t, st = m.parse(buf)
print(f'{w}x{h}')
for y, row in enumerate(g):
    print(y, ' | '.join(repr(o) if o not in (None,) else '.' for o in row))
print('tail', t.hex(' '))
