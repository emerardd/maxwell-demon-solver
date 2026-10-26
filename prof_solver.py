"""Profile the solver on one level for a fixed number of states. Usage: prof_solver.py GAME_DIR LEVEL [states]"""
import cProfile, os, pstats, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mxw, solver

levels = mxw.load_world(sys.argv[1])[0]
sv = solver.Solver(levels, max_states=int(sys.argv[3]) if len(sys.argv) > 3 else 20_000)
prof = cProfile.Profile()
prof.enable()
try:
    sv.solve(sys.argv[2])
except RuntimeError as e:
    print(e)
prof.disable()
pstats.Stats(prof).sort_stats('cumulative').print_stats(14)
