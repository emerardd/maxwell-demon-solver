"""Play a stored plan in the running game by sending key presses (Windows).

The plan is replayed through the rules first, so every key press knows what it causes in the
game: a plain move, extra piston steps (each one more short animation), solving the level, or
entering and quitting levels. Waits follow from that instead of one fixed interval per key.

Safety: keys are only sent while the game's window is in front. If it loses focus the player
pauses until it is back; holding F8 stops it. Nothing reads the game itself, so whether the
level was solved is for the person watching to say.
"""
import json, os, time
from . import sim, solver, store

GAME_EXE = "maxwell's_demon.exe"
KEY = {'L': 'A', 'D': 'S', 'R': 'D', 'U': 'W'}
# milliseconds, measured on one machine; override in timing.json at the repository root
TIMING = {
    'press': 80,      # key held down
    'move': 170,      # after a move
    'piston': 150,    # per extra piston step after a move
    'win': 1400,      # after the move that solves the level
    'enter': 650,     # after entering a level
    'quit': 400,      # after quitting a level
    'before_quit': 60,  # extra after the move before a quit (quitting is refused earlier)
}


def timing():
    t = dict(TIMING)
    path = os.path.join(store.ROOT, 'timing.json')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            t.update(json.load(f))
    return t


def actions(levels, lid, plan, ctx=None):
    """[(key, kind, extra)] for a plan: key 'W'/'A'/'S'/'D'/'E'/'Q'; kind 'move', 'win', 'enter'
    or 'quit'; extra the number of extra piston steps after a move. Raises ValueError when the
    plan does not replay."""
    sv = solver.Solver(levels)
    w = sv.world
    kw = store.solve_kwargs(ctx or {})
    h = w.start(kw.get('scope') or lid, kw.get('solved', frozenset()), kw.get('t_out', sim.NEUTRAL))
    out = []
    for step in store.unflatten(plan) if isinstance(plan, str) else plan:
        if isinstance(step, str):
            for letter in step:
                m = w.current(h)
                h = w.step(h, sim.DIR_NAMES.index(letter))
                if h is None:
                    raise ValueError(f'the plan does not replay: move {len(out) + 1} is impossible')
                done = not h.path or w.finished(h, lid)
                out.append((KEY[letter], 'win' if done else 'move', m.last_extra))
                if done:
                    return out
        elif step[0] == 'enter':
            h = w.enter(h, sim.DIR_NAMES.index(step[1]))
            out.append(('E', 'enter', 0))
        else:
            h = w.quit(h)
            out.append(('Q', 'quit', 0))
        if h is None:
            raise ValueError('the plan does not replay')
    raise ValueError('the plan does not solve the level')


def schedule(acts, t=None):
    """[(key, milliseconds to wait after pressing it)]."""
    t = t or timing()
    out = []
    for i, (key, kind, extra) in enumerate(acts):
        wait = t[kind] + extra * t['piston']
        if i + 1 < len(acts) and acts[i + 1][1] == 'quit':
            wait += t['before_quit']
        out.append((key, wait))
    return out


def tas_text(acts):
    """The keys in the syntax of WYXkk/Maxwell-s-TAS-demon: wasd/e/q, p per piston step, '-'
    for the win animation, upper case for the longer wait before quitting."""
    out = []
    for i, (key, kind, extra) in enumerate(acts):
        k = key.lower()
        if i + 1 < len(acts) and acts[i + 1][1] == 'quit':
            k = k.upper()
        out.append(k + 'p' * extra + ('-' if kind == 'win' else '') + ('\n' if kind in ('enter', 'quit') else ''))
    return out


class Player:
    """Sends key presses to the game window (Windows only)."""
    STOP = 0x77  # F8

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.user32, self.kernel32 = ctypes.WinDLL('user32'), ctypes.WinDLL('kernel32')
        self.ctypes, self.wintypes = ctypes, wintypes

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                        ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]

        class INPUT(ctypes.Structure):
            class _U(ctypes.Union):
                _fields_ = [('ki', KEYBDINPUT), ('pad', ctypes.c_byte * 32)]
            _anonymous_ = ('u',)
            _fields_ = [('type', wintypes.DWORD), ('u', _U)]
        self.INPUT, self.KEYBDINPUT = INPUT, KEYBDINPUT

    def game_in_front(self):
        hwnd = self.user32.GetForegroundWindow()
        if not hwnd:
            return False
        pid = self.wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, self.ctypes.byref(pid))
        proc = self.kernel32.OpenProcess(0x1000, False, pid.value)  # query limited information
        if not proc:
            return False
        try:
            buf = self.ctypes.create_unicode_buffer(1024)
            size = self.wintypes.DWORD(len(buf))
            if not self.kernel32.QueryFullProcessImageNameW(proc, 0, buf, self.ctypes.byref(size)):
                return False
            return os.path.basename(buf.value).lower() == GAME_EXE
        finally:
            self.kernel32.CloseHandle(proc)

    def stop_held(self):
        return bool(self.user32.GetAsyncKeyState(self.STOP) & 0x8000)

    def _key(self, vk, up):
        inp = self.INPUT(type=1)  # keyboard
        inp.ki = self.KEYBDINPUT(wVk=vk, wScan=0, dwFlags=2 if up else 0, time=0, dwExtraInfo=0)
        self.user32.SendInput(1, self.ctypes.byref(inp), self.ctypes.sizeof(self.INPUT))

    def press(self, key, hold_ms):
        self._key(ord(key), False)
        time.sleep(hold_ms / 1000)
        self._key(ord(key), True)

    def wait_for_game(self, log, timeout=60):
        """Wait until the game window is in front. False on timeout or F8."""
        end = time.time() + timeout
        while not self.game_in_front():
            if self.stop_held() or time.time() > end:
                return False
            time.sleep(0.1)
        return True

    def play(self, sched, log=print, t=None):
        """Press the keys of sched. Returns the number of keys sent (less than all when
        stopped with F8)."""
        t = t or timing()
        for i, (key, wait) in enumerate(sched):
            if self.stop_held():
                log(f'F8：在第 {i + 1}/{len(sched)} 键前停止')
                return i
            if not self.game_in_front():
                log('游戏窗口不在前台，暂停；切回游戏后继续（按住 F8 放弃）')
                if not self.wait_for_game(log, timeout=600):
                    log(f'放弃，已发送 {i}/{len(sched)} 键')
                    return i
                time.sleep(0.5)
            self.press(key, t['press'])
            time.sleep(max(0, wait - t['press']) / 1000)
            if (i + 1) % 10 == 0 or i + 1 == len(sched):
                log(f'[{i + 1}/{len(sched)}]')
        return len(sched)
