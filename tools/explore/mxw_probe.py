"""Probe parser for Maxwell's puzzling demon .mxw files (format reverse-engineered by hypothesis)."""
import sys, os, collections

INNER_BIT = int(os.environ.get('INNER_BIT', '0'))

class Bad(Exception):
    pass

def parse(buf):
    p = 0
    def rd():
        nonlocal p
        if p >= len(buf):
            raise Bad("eof")
        b = buf[p]; p += 1
        return b
    def rd_str():
        nonlocal p
        e = buf.index(0, p)
        s = buf[p:e].decode('ascii'); p = e + 1
        return s
    def rd_obj(stats):
        tag = rd()
        stats[tag] += 1
        if tag == 0:
            return None
        if tag == 1:
            return ('start',)
        if tag == 2:
            return ('block', rd(), rd())
        if tag == 3:
            flag = rd(); lid = rd_str()
            a = rd_obj(stats); b = rd_obj(stats)
            return ('level', flag, lid, a, b)
        if tag == 4:
            state = rd()
            stats[('pstate', state)] += 1
            body = rd_obj(stats)
            side = rd()
            inner = rd_obj(stats) if state & INNER_BIT else None
            return ('piston', state, body, side, inner)
        if tag == 5:
            return ('head', rd(), rd(), rd())
        raise Bad(f"tag {tag:#x} at {p-1}")
    stats = collections.Counter()
    w, h = rd(), rd()
    grid = [[rd_obj(stats) for _ in range(w)] for _ in range(h)]
    return w, h, grid, buf[p:], stats

if __name__ == '__main__':
    d = sys.argv[1]
    ok = 0; fails = collections.Counter(); tails = collections.Counter(); attrs = collections.Counter(); sides = collections.Counter()
    first_fail = {}; pst = collections.Counter()
    for f in sorted(os.listdir(d)):
        if not f.endswith('.mxw'):
            continue
        buf = open(os.path.join(d, f), 'rb').read()
        try:
            w, h, grid, tail, st = parse(buf)
            ok += 1
            tails[len(tail)] += 1
            pst.update({k: v for k, v in st.items() if isinstance(k, tuple)})
            def walk(o):
                if o and o[0] == 'block':
                    attrs[o[1]] += 1; sides[o[2]] += 1
                if o and o[0] == 'level':
                    walk(o[3]); walk(o[4])
            for row in grid:
                for o in row:
                    walk(o)
        except Exception as e:
            k = str(e).split(' at ')[0]
            fails[k] += 1
            first_fail.setdefault(k, (f, str(e)))
    print('ok', ok, 'fail', sum(fails.values()))
    print('fails', fails.most_common(10))
    for k, v in list(first_fail.items())[:8]:
        print('  e.g.', k, v)
    print('tail lengths', tails.most_common(10))
    print('attr bytes', sorted((hex(k), v) for k, v in attrs.items()))
    print('piston states', sorted((hex(k[1]), v) for k, v in pst.items()))
    print('side bytes', sorted((hex(k), v) for k, v in sides.items())[:40])
