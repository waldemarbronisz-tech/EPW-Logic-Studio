"""Orthogonal wire routing with obstacle avoidance.

WireItem.update_path() already guarantees the correct EXIT/ENTRY
direction at each end (a fixed "stub" segment pointing out of whichever
side the pin is actually mounted on — see wire_item.py's _port_facing()).
What it didn't do is avoid running straight through another block's body
in between — this module adds that, as a fallback: the plain 1-2-bend
path between the two stub points (candidate_path()) is tried FIRST and
used as-is whenever it's already clear (the overwhelming common case,
and exactly as cheap as before this module existed); a grid-based A*
search (astar_route()) only runs for the wires that actually need it —
mostly backward/feedback connections in a tight layout — so a project
with many blocks doesn't pay pathfinding cost on every drag frame for
wires that were never going to cross anything anyway.

feat/wire-detour-and-text-size §A1/§A2: a wire's own source/dest
block(s) used to be UNCONDITIONALLY exempt from every obstacle list
(wire_item.py::_obstacle_rects()) — correct for the tiny stub segment
right at the port (drawn directly in update_path(), never even reaching
this module), wrong for the rest of that block's own body, which a
routed wire could then freely cut straight through. That exemption is
gone: every block is a real obstacle now, including a wire's own
source/dest. The one case this alone doesn't handle well is a
self-loop (a block's output wired back to its OWN input, §A2) — general
A*'s tie-breaking has no notion of "prefer the side with more free
space", so route_self_loop() below is a small, deterministic, purpose-
built router for exactly that shape: right from the output, over or
under the block's own body (whichever side has more room; ties go
up), back in from the left.
"""
import heapq
import math

from PySide6.QtCore import QPointF, QRectF

from logic_studio.core.grid import GRID_SIZE

# feat/wire-detour-and-text-size §A2: "at least one grid cell" of
# clearance between a routed wire and any block's outline — used as the
# default obstacle-inflation margin everywhere in this module (was a
# bare 6.0 in two places before this, less than one grid cell and not
# tied to the same constant the rest of the app snaps block positions
# to). A stub's own fixed 15px offset (wire_item.py) still clears this
# margin comfortably (15 > 10), so a wire's own final approach segment
# is never mistaken for crossing its own, now-no-longer-exempt source/
# dest block — see routing.py's own module docstring update below.
_OBSTACLE_MARGIN = GRID_SIZE


def candidate_path(start: QPointF, end: QPointF) -> list:
    """The plain 1-2-bend Manhattan path between two already-facing-the-
    right-way points — a straight line when they're level, one vertical
    bend at the horizontal midpoint otherwise. This is the ENTIRE routing
    algorithm before obstacle avoidance existed; still the fast, default
    path whenever it happens not to cross anything."""
    if abs(start.y() - end.y()) < 0.5:
        return [start, end]
    mid_x = (start.x() + end.x()) / 2.0
    return [start, QPointF(mid_x, start.y()), QPointF(mid_x, end.y()), end]


def _segment_intersects_rect(p1: QPointF, p2: QPointF, rect: QRectF) -> bool:
    """True if the straight segment p1->p2 enters `rect`. Every segment
    this module ever produces is axis-aligned (horizontal or vertical) —
    a general polygon/rect intersection test isn't needed."""
    x1, y1, x2, y2 = p1.x(), p1.y(), p2.x(), p2.y()
    if abs(y1 - y2) < 1e-6:  # horizontal
        if not (rect.top() <= y1 <= rect.bottom()):
            return False
        lo, hi = (x1, x2) if x1 <= x2 else (x2, x1)
        return hi >= rect.left() and lo <= rect.right()
    if abs(x1 - x2) < 1e-6:  # vertical
        if not (rect.left() <= x1 <= rect.right()):
            return False
        lo, hi = (y1, y2) if y1 <= y2 else (y2, y1)
        return hi >= rect.top() and lo <= rect.bottom()
    # Never actually produced (every path here is orthogonal), but a
    # coarse bounding-box check beats silently reporting "no collision"
    # for a genuinely diagonal input.
    seg_rect = QRectF(QPointF(min(x1, x2), min(y1, y2)), QPointF(max(x1, x2), max(y1, y2)))
    return seg_rect.intersects(rect)


def path_intersects_obstacles(waypoints: list, obstacles: list, margin: float = _OBSTACLE_MARGIN) -> bool:
    """True if any segment of `waypoints` enters any rect in `obstacles`
    (each inflated by `margin`, so a wire doesn't visually hug a block's
    edge even when it technically clears it)."""
    if not obstacles:
        return False
    inflated = [r.adjusted(-margin, -margin, margin, margin) for r in obstacles]
    for i in range(len(waypoints) - 1):
        p1, p2 = waypoints[i], waypoints[i + 1]
        for rect in inflated:
            if _segment_intersects_rect(p1, p2, rect):
                return True
    return False


_DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1))
_TURN_PENALTY = 4  # grid-steps — enough to prefer a straight run over a
                    # zig-zag of the same total length, not so much that a
                    # genuinely necessary detour gets refused.
_PAD_CELLS = 14     # search region = start/end's own bounding box, plus
                    # this many cells of slack on every side — enough to
                    # go around one or two blocks, bounded so two very
                    # distant endpoints can't blow up the search.
_MAX_CELLS = 60000  # safety cap on total grid cells explored; beyond
                    # this, astar_route() gives up and returns None so
                    # the caller falls back to the plain candidate_path().


def astar_route(start: QPointF, end: QPointF, obstacles: list, cell_size: float = GRID_SIZE):
    """4-directional grid search from `start` to `end` avoiding every rect
    in `obstacles`, returning a simplified (collinear runs merged) list of
    QPointF waypoints — or None if no path was found within the bounded
    search region (caller should fall back to candidate_path() rather
    than leave a wire unrouted).

    The grid's origin is `start` itself, in BOTH axes — since every wire
    endpoint this is ever called with is a "stub" point (pin position +/-
    a fixed offset in one axis only, see wire_item.py), the offset
    between any two such points is always an exact multiple of a 10px
    grid step, so this origin choice makes both `start` and `end`
    round-trip through the grid EXACTLY, with no rounding-induced gap at
    either end — no special-casing needed to weld the search result back
    onto the caller's own exact endpoints."""
    if not obstacles:
        return None  # nothing to avoid — let the caller use candidate_path()

    def to_cell(pt):
        return (round((pt.x() - start.x()) / cell_size), round((pt.y() - start.y()) / cell_size))

    def to_point(cell):
        return QPointF(start.x() + cell[0] * cell_size, start.y() + cell[1] * cell_size)

    start_cell = (0, 0)
    end_cell = to_cell(end)

    min_cx = min(0, end_cell[0]) - _PAD_CELLS
    max_cx = max(0, end_cell[0]) + _PAD_CELLS
    min_cy = min(0, end_cell[1]) - _PAD_CELLS
    max_cy = max(0, end_cell[1]) + _PAD_CELLS
    if (max_cx - min_cx) * (max_cy - min_cy) > _MAX_CELLS:
        return None

    inflated = [r.adjusted(-_OBSTACLE_MARGIN, -_OBSTACLE_MARGIN, _OBSTACLE_MARGIN, _OBSTACLE_MARGIN) for r in obstacles]

    def blocked(cell):
        p = to_point(cell)
        for r in inflated:
            if r.left() <= p.x() <= r.right() and r.top() <= p.y() <= r.bottom():
                return True
        return False

    def heuristic(cell):
        return abs(cell[0] - end_cell[0]) + abs(cell[1] - end_cell[1])

    start_state = (start_cell, None)
    open_heap = [(heuristic(start_cell), 0, start_state)]
    came_from = {}
    best_g = {start_state: 0}

    while open_heap:
        _f, g, state = heapq.heappop(open_heap)
        cell, in_dir = state
        if cell == end_cell:
            return _simplify_collinear(_reconstruct(came_from, state, to_point))
        if g > best_g.get(state, float("inf")):
            continue  # a cheaper route to this exact (cell, direction) was already popped
        for d in _DIRECTIONS:
            n_cell = (cell[0] + d[0], cell[1] + d[1])
            if not (min_cx <= n_cell[0] <= max_cx and min_cy <= n_cell[1] <= max_cy):
                continue
            if n_cell != end_cell and blocked(n_cell):
                continue
            turn_cost = 0 if in_dir in (None, d) else _TURN_PENALTY
            n_g = g + 1 + turn_cost
            n_state = (n_cell, d)
            if n_g < best_g.get(n_state, float("inf")):
                best_g[n_state] = n_g
                came_from[n_state] = state
                heapq.heappush(open_heap, (n_g + heuristic(n_cell), n_g, n_state))

    return None  # boxed in within the search region — caller falls back


def _reconstruct(came_from: dict, state, to_point) -> list:
    cells = [state[0]]
    while state in came_from:
        state = came_from[state]
        cells.append(state[0])
    cells.reverse()
    return [to_point(c) for c in cells]


def _simplify_collinear(points: list) -> list:
    """Drops every waypoint that sits in the MIDDLE of a straight run —
    A* naturally emits one point per grid step, which would otherwise
    render as (harmless but wasteful) collinear sub-segments instead of
    one clean line per actual bend."""
    if len(points) < 3:
        return points
    simplified = [points[0]]
    for i in range(1, len(points) - 1):
        prev, cur, nxt = simplified[-1], points[i], points[i + 1]
        same_x = prev.x() == cur.x() == nxt.x()
        same_y = prev.y() == cur.y() == nxt.y()
        if same_x or same_y:
            continue  # `cur` is redundant — the run continues straight through it
        simplified.append(cur)
    simplified.append(points[-1])
    return simplified


def route(start: QPointF, end: QPointF, obstacles: list) -> list:
    """The one entry point wire_item.py calls: candidate_path() if it's
    already clear (the common, cheap case), else astar_route() around
    every obstacle, else candidate_path() again as a last resort (a wire
    that visually crosses a block is still better than one that silently
    fails to appear or raises)."""
    simple = candidate_path(start, end)
    if not path_intersects_obstacles(simple, obstacles):
        return simple
    routed = astar_route(start, end, obstacles)
    return routed if routed else simple


def _round_away(base: float, target: float, cell_size: float, direction: int) -> float:
    """The smallest `base + k*cell_size` (k a positive integer) that is at
    least as far from `base`, in `direction` (-1 toward smaller Y/"up",
    +1 toward larger Y/"down"), as `target` — on the SAME relative grid
    astar_route() already uses (anchored at the wire's own stub point,
    not absolute scene coordinates — see this module's own docstring),
    so a self-loop's detour bend points land exactly where a general A*
    route's would. Always moves at least one full cell_size step, even if
    `target` technically needs less — a detour landing back on `base`
    itself would defeat the whole point of routing around something."""
    delta = (target - base) * direction
    steps = max(1, math.ceil(delta / cell_size))
    return base + direction * steps * cell_size


def _free_vertical_space(rect: QRectF, obstacles: list, direction: int, cap: float = 2000.0) -> float:
    """Distance from `rect`'s own top (direction=-1) or bottom
    (direction=+1) edge to the nearest OTHER obstacle that overlaps its
    horizontal extent — capped at `cap` so "nothing up there for 50
    screens" doesn't out-rank a genuinely tighter but still-clear gap on
    the other side by an arbitrary amount; only which side has MORE room
    within a sane visible range matters for §A2's side choice."""
    edge = rect.top() if direction == -1 else rect.bottom()
    best = cap
    for obstacle in obstacles:
        if obstacle.right() <= rect.left() or obstacle.left() >= rect.right():
            continue  # no horizontal overlap with `rect` -- irrelevant to this gap
        gap = (edge - obstacle.bottom()) if direction == -1 else (obstacle.top() - edge)
        if gap >= 0:
            best = min(best, gap)
    return best


def route_self_loop(start: QPointF, end: QPointF, own_rect: QRectF, obstacles: list,
                     cell_size: float = GRID_SIZE, clearance: float = GRID_SIZE) -> list:
    """feat/wire-detour-and-text-size §A2: `start`/`end` are a block's own
    output/input stubs (already padded outward by wire_item.py). Routes
    up-and-over or down-and-under `own_rect` — never through it, and
    never running FLUSH along it either — choosing whichever side has
    more free vertical space (ties go to "up", the smaller-Y side, per
    §A2), with at least `clearance` (default one grid cell) between the
    detour and the block's own outline on every side it passes, snapped
    outward to the nearest grid line so it never ends up closer than
    that minimum after rounding.

    A stub lands exactly ON its own block's edge by this app's own
    convention (the port itself is inset from the block's true
    sceneBoundingRect() by the same fixed distance wire_item.py's own
    stub offset then re-adds — confirmed directly, not assumed; see
    wire_item.py::_obstacle_rects()'s docstring) — so the vertical riser
    right at `start.x()`/`end.x()` would otherwise run exactly along that
    edge, touching it, not clearing it. Each riser is pushed `clearance`
    further out (away from own_rect's own horizontal center) BEFORE
    turning to cross above/below — six points, five segments, still
    fully orthogonal (§A3).

    `own_rect` is handled directly here, NOT via `obstacles` — the caller
    should not include the self-loop's own block in that list. Returns
    None if BOTH sides are blocked by some OTHER obstacle in the way, so
    the caller can fall back to the general route()/astar_route() around
    every obstacle including this block's own body."""
    free_up = _free_vertical_space(own_rect, obstacles, direction=-1)
    free_down = _free_vertical_space(own_rect, obstacles, direction=1)
    sides = (-1, 1) if free_up >= free_down else (1, -1)  # tie -> up first

    center_x = own_rect.center().x()
    start_out = 1 if start.x() >= center_x else -1  # which way is "away from the block" for this stub
    end_out = 1 if end.x() >= center_x else -1
    riser_start = QPointF(start.x() + start_out * clearance, start.y())
    riser_end = QPointF(end.x() + end_out * clearance, end.y())

    for direction in sides:
        target = (own_rect.top() - clearance) if direction == -1 else (own_rect.bottom() + clearance)
        detour_y = _round_away(start.y(), target, cell_size, direction)
        detour_top = QPointF(riser_start.x(), detour_y)
        detour_bottom = QPointF(riser_end.x(), detour_y)
        path = [start, riser_start, detour_top, detour_bottom, riser_end, end]
        # own_rect is checked only against the DETOUR itself (riser_start
        # -> ... -> riser_end) — the two outer segments (start->riser_start,
        # riser_end->end) start/end exactly ON own_rect's own edge BY
        # DESIGN (see this function's docstring) and always register as
        # "touching" a margin=0 check at that shared boundary; that's the
        # same "final approach segment" §A1 explicitly exempts, not a
        # real crossing. `obstacles` (every OTHER block) still checks the
        # FULL path, outer segments included -- a real third-party
        # obstacle right next to this block's own port is still a real
        # collision.
        if not path_intersects_obstacles(path, obstacles) and \
                not path_intersects_obstacles([riser_start, detour_top, detour_bottom, riser_end],
                                               [own_rect], margin=0):
            return path
    return None
