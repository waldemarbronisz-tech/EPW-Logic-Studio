"""feat/wire-routing-obstacle-avoidance — ui/canvas/routing.py's grid-
based A* fallback, and its integration into WireItem.update_path().

The plain 1-2-bend path (routing.candidate_path(), the entire routing
algorithm before this module existed) is still tried FIRST and used as-is
whenever it's already clear — these tests cover the NEW behavior:
detecting when it isn't, and routing around obstacles when it matters.
"""
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF, QRectF

from logic_studio.blocks import register_builtin_blocks
from logic_studio.ui.canvas import routing

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---- candidate_path() -------------------------------------------------

def test_candidate_path_is_a_straight_line_when_level():
    path = routing.candidate_path(QPointF(0, 100), QPointF(200, 100))
    assert path == [QPointF(0, 100), QPointF(200, 100)]

def test_candidate_path_is_a_single_bend_otherwise():
    path = routing.candidate_path(QPointF(0, 100), QPointF(200, 300))
    assert len(path) == 4
    assert path[0] == QPointF(0, 100)
    assert path[-1] == QPointF(200, 300)
    mid_x = path[1].x()
    assert path[1] == QPointF(mid_x, 100)
    assert path[2] == QPointF(mid_x, 300)


# ---- path_intersects_obstacles() ---------------------------------------

def test_horizontal_segment_crossing_a_rect_is_detected():
    waypoints = [QPointF(0, 100), QPointF(200, 100)]
    obstacle = QRectF(80, 80, 40, 40)  # spans y 80-120, x 80-120 -- crosses y=100
    assert routing.path_intersects_obstacles(waypoints, [obstacle], margin=0) is True

def test_horizontal_segment_clear_of_a_rect_is_not_detected():
    waypoints = [QPointF(0, 100), QPointF(200, 100)]
    obstacle = QRectF(80, 200, 40, 40)  # well below the segment
    assert routing.path_intersects_obstacles(waypoints, [obstacle], margin=0) is False

def test_vertical_segment_crossing_a_rect_is_detected():
    waypoints = [QPointF(100, 0), QPointF(100, 200)]
    obstacle = QRectF(80, 80, 40, 40)
    assert routing.path_intersects_obstacles(waypoints, [obstacle], margin=0) is True

def test_margin_inflates_the_obstacle():
    waypoints = [QPointF(0, 100), QPointF(200, 100)]
    obstacle = QRectF(80, 105, 40, 40)  # 5px below the segment -- clear at margin 0
    assert routing.path_intersects_obstacles(waypoints, [obstacle], margin=0) is False
    assert routing.path_intersects_obstacles(waypoints, [obstacle], margin=10) is True

def test_no_obstacles_never_intersects():
    waypoints = [QPointF(0, 100), QPointF(200, 100)]
    assert routing.path_intersects_obstacles(waypoints, [], margin=6) is False


# ---- astar_route() -------------------------------------------------------

def test_astar_returns_none_with_no_obstacles():
    """route() itself never calls astar_route() when there's nothing to
    avoid — this locks in that astar_route() alone is also a no-op then,
    so a future caller can't accidentally rely on it for the plain case."""
    assert routing.astar_route(QPointF(0, 0), QPointF(200, 0), []) is None

def test_astar_finds_a_path_that_avoids_a_blocking_obstacle():
    start = QPointF(0, 100)
    end = QPointF(300, 100)
    obstacle = QRectF(100, 50, 100, 100)  # sits squarely across the direct line
    path = routing.astar_route(start, end, [obstacle])
    assert path is not None
    assert path[0] == start
    assert path[-1] == end
    assert routing.path_intersects_obstacles(path, [obstacle]) is False

def test_astar_path_is_orthogonal_only():
    start = QPointF(0, 100)
    end = QPointF(300, 300)
    obstacle = QRectF(100, 150, 100, 100)
    path = routing.astar_route(start, end, [obstacle])
    assert path is not None
    for i in range(len(path) - 1):
        p1, p2 = path[i], path[i + 1]
        assert p1.x() == p2.x() or p1.y() == p2.y()  # never diagonal

def test_astar_endpoints_are_exact_no_rounding_drift():
    """§ design note in routing.py: the grid origin is `start` itself, and
    every stub-to-stub offset this is ever called with is an exact
    multiple of the grid step — start/end must round-trip EXACTLY, not
    just "close enough", or the routed path would visibly not quite touch
    the pin's own stub point."""
    start = QPointF(515.0, 200.0)  # a typical stub x (pin x=500 + 15 offset)
    end = QPointF(185.0, 350.0)
    obstacle = QRectF(250, 220, 80, 80)
    path = routing.astar_route(start, end, [obstacle])
    assert path is not None
    assert path[0].x() == start.x() and path[0].y() == start.y()
    assert path[-1].x() == end.x() and path[-1].y() == end.y()

def test_astar_gives_up_gracefully_on_a_huge_search_region():
    """Two endpoints far enough apart that the bounded grid search would
    exceed its cell cap must return None (caller falls back), not hang or
    raise."""
    start = QPointF(0, 0)
    end = QPointF(50000, 50000)
    obstacle = QRectF(100, 100, 50, 50)
    assert routing.astar_route(start, end, [obstacle]) is None


# ---- route() — the entry point wire_item.py actually calls ---------------

def test_route_uses_the_candidate_path_when_already_clear():
    start, end = QPointF(0, 100), QPointF(200, 100)
    obstacle = QRectF(80, 300, 40, 40)  # nowhere near the direct line
    result = routing.route(start, end, [obstacle])
    assert result == routing.candidate_path(start, end)

def test_route_avoids_an_obstacle_the_candidate_path_would_cross():
    start, end = QPointF(0, 100), QPointF(300, 100)
    obstacle = QRectF(100, 50, 100, 100)
    result = routing.route(start, end, [obstacle])
    assert routing.path_intersects_obstacles(result, [obstacle]) is False
    assert result != routing.candidate_path(start, end)

def test_route_falls_back_to_candidate_path_when_astar_cannot_find_one():
    """A pathological case (search region far too large to bound) must
    still return SOMETHING usable, not None/empty — the caller has no
    other fallback of its own."""
    start, end = QPointF(0, 0), QPointF(50000, 50000)
    obstacle = QRectF(100, 100, 50, 50)  # blocks the direct candidate path
    result = routing.route(start, end, [obstacle])
    assert result == routing.candidate_path(start, end)
