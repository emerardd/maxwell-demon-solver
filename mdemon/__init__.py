"""Maxwell's puzzling demon: level files, rules and solvers.

    mxw       level file format (world/*.mxw, structure.json)
    sim       rules inside one level: pushing, sticky faces, heat, goals
    world     rules between levels: entering, exiting, nesting
    prune     static push-distance tables and heuristics
    solver    A* over whole world states, solve_any, replay
    catalog   worlds and their level lists
    staged    staged sub-goal search
    derive    deriving the final layout and stage order of a shuffle level
    report    step-by-step walkthroughs
    context   starting a search inside a level's real parent
"""
