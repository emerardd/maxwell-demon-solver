"""Solution database: every plan the solver scripts found, the shortest per level, and which
plans were played through in the game.

solutions/db.json maps level id -> {
    "plans":    {plan: {"moves", "found" (date), "sources" [...], "ctx" {...}}},
    "verified": {plan: date}       plans that were checked in the game
}
A plan is solver.flatten() text: LDRU moves, [E<dir>] entering, [Q] quitting. ctx holds what
the plan needs besides the level's start (solved, t_out, scope; see solver.Solver.solve).
Several scripts may run at once, so every change re-reads the file under a lock file.
"""
import datetime, json, os, re, time
from contextlib import contextmanager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, 'solutions', 'db.json')


def moves(plan):
    """Key presses of a flattened plan: one per move, entry and quit."""
    return len(re.findall(r'\[E.\]|\[Q\]|[LDRU]', plan))


def unflatten(plan):
    """solver.flatten() text back to a plan (list of move strings and ('enter', d) / ('quit',))."""
    out = []
    for tok in re.findall(r'\[E(.)\]|(\[Q\])|([LDRU]+)', plan):
        if tok[0]:
            out.append(('enter', tok[0]))
        elif tok[1]:
            out.append(('quit',))
        else:
            out.append(tok[2])
    return out


def ctx_of(solved=frozenset(), t_out=0, scope=None):
    """The non-default parts of a solve() context, JSON-friendly."""
    ctx = {}
    if solved:
        ctx['solved'] = sorted(solved)
    if t_out:
        ctx['t_out'] = t_out
    if scope:
        ctx['scope'] = scope
    return ctx


def solve_kwargs(ctx):
    """ctx back to keyword arguments for solver.Solver.solve / solver.replay."""
    kw = dict(ctx)
    if 'solved' in kw:
        kw['solved'] = frozenset(kw['solved'])
    return kw


@contextmanager
def _locked(path=DB):
    lock = path + '.lock'
    for _ in range(600):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.time() - os.path.getmtime(lock) > 60:  # left behind by a killed process
                os.remove(lock)
            time.sleep(0.05)
    else:
        raise TimeoutError(f'{lock} is held')
    try:
        os.close(fd)
        yield
    finally:
        os.remove(lock)


def load(path=DB):
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _save(db, path=DB):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write('\n')
    os.replace(tmp, path)


def _today():
    return datetime.date.today().isoformat()


def record(lid, plan, ctx=None, source='', path=DB):
    """Add a plan (list or flattened text) found for lid. Returns True when it is the shortest
    known plan for the level now (a new best or equal to it)."""
    from .solver import flatten
    text = plan if isinstance(plan, str) else flatten(plan)
    with _locked(path):
        db = load(path)
        entry = db.setdefault(lid, {'plans': {}, 'verified': {}})
        p = entry['plans'].get(text)
        if p is None:
            p = entry['plans'][text] = {'moves': moves(text), 'found': _today(), 'sources': [],
                                        'ctx': ctx or {}}
        if source and source not in p['sources']:
            p['sources'].append(source)
        _save(db, path)
        return p['moves'] <= min(q['moves'] for q in entry['plans'].values())


def best(entry):
    """(plan, info) of the shortest plan of a db entry; verified plans win ties."""
    return min(entry['plans'].items(),
               key=lambda kv: (kv[1]['moves'], kv[0] not in entry['verified'], kv[0]))


def verify(lid, plan=None, path=DB):
    """Mark a plan of lid (default: its current best) as played through in the game. Returns
    the plan."""
    with _locked(path):
        db = load(path)
        entry = db.get(lid)
        if entry is None or not entry['plans']:
            raise KeyError(f'no plan stored for {lid}')
        text = plan or best(entry)[0]
        if text not in entry['plans']:
            raise KeyError(f'{lid} has no stored plan {text}')
        entry['verified'][text] = _today()
        _save(db, path)
        return text
