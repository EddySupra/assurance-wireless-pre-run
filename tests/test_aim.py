"""Tests for working out where on the physical screen to click.

This is the step that decides whether --real-input can act at all, and it fails
closed: no point means no click, and the lead stops rather than the pointer
landing somewhere unintended. That makes a *wrong* refusal expensive, which is
what these cover -- a control in plain view must not be judged unreachable.

    python -m pytest tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot import real_input  # noqa: E402

VIEWPORT = {"x": 0.0, "y": 100.0, "w": 1440, "h": 900, "fx": 0.0, "fy": 0.0}


class _Sb:
    """Answers the three scripts screen_point runs, in order."""

    def __init__(self, box, *, origin=None, hit=True):
        self.box = box
        self.origin = dict(origin or VIEWPORT)
        self.hit = hit
        self.hit_points = []

    def execute_script(self, script, *args):
        if "getBoundingClientRect" in script:
            return dict(self.box)
        if "elementFromPoint" in script:
            self.hit_points.append((args[1], args[2]))
            return {"hit": self.hit, "what": "something.else"}
        return dict(self.origin)


def _aim(box, **kw):
    sb = _Sb(box, **kw)
    real_input.set_frame_origin(None)
    return real_input.screen_point(sb, object()), sb


def test_a_button_in_plain_view_is_aimed_at():
    point, _ = _aim({"x": 600.0, "y": 400.0, "w": 180.0, "h": 48.0})
    assert point is not None
    x, y = point
    # Inside the button, offset by the viewport's screen origin.
    assert 600 <= x <= 780
    assert 500 <= y <= 548


def test_an_element_hanging_below_the_fold_is_still_aimed_at():
    """The regression that stopped every lead at the Apply Now button.

    The check used to reject on the element's top-left corner being outside
    the viewport. A tall element whose top sits above the fold, or one that
    extends past the bottom, was refused while plainly visible and clickable.
    """
    point, _ = _aim({"x": 600.0, "y": 850.0, "w": 180.0, "h": 200.0})
    assert point is not None


def test_an_element_starting_above_the_fold_is_still_aimed_at():
    point, _ = _aim({"x": 600.0, "y": -120.0, "w": 180.0, "h": 260.0})
    assert point is not None


def test_the_aim_lands_in_the_visible_part_not_the_hidden_part():
    """Aiming at the true centre of a half-scrolled element misses the screen."""
    # Only the bottom 100px of this element is on screen (y from 0 to 100).
    box = {"x": 600.0, "y": -400.0, "w": 180.0, "h": 500.0}
    for _ in range(25):
        point, sb = _aim(box)
        assert point is not None
        doc_y = sb.hit_points[-1][1]
        assert 0.0 <= doc_y <= 100.0, doc_y


def test_an_element_entirely_off_screen_is_refused():
    point, _ = _aim({"x": 600.0, "y": 2000.0, "w": 180.0, "h": 48.0})
    assert point is None


def test_a_sliver_too_thin_to_hit_is_refused():
    """Two visible pixels is not something a hand could hit either."""
    point, _ = _aim({"x": 600.0, "y": 898.0, "w": 180.0, "h": 48.0})
    assert point is None


def test_an_element_with_no_size_is_refused():
    assert _aim({"x": 10.0, "y": 10.0, "w": 0.0, "h": 0.0})[0] is None


def test_something_covering_the_target_is_refused():
    """A real click hits whatever is on top, silently. Refuse instead."""
    point, _ = _aim({"x": 600.0, "y": 400.0, "w": 180.0, "h": 48.0}, hit=False)
    assert point is None


def test_state_from_the_last_browser_does_not_survive_into_the_next():
    """The bug that failed the second lead of every run, and only the second.

    The frame offset is module-level, so it described whichever browser last
    entered the enrollment frame. Lead one recorded it; lead two then started
    on the public pages with that offset still in force, computed every screen
    coordinate as though a frame were open, and refused the Apply Now button
    as unreachable. Lead one always worked, which is what made it look like a
    site problem rather than leaked state.
    """
    real_input.set_frame_origin({"x": 0.0, "y": 0.0, "w": 800, "h": 600,
                                 "fx": 500.0, "fy": 400.0})
    real_input.reset_for_new_session()

    sb = _Sb({"x": 600.0, "y": 400.0, "w": 180.0, "h": 48.0})
    point = real_input.screen_point(sb, object())
    assert point is not None, "a fresh session must not inherit a frame offset"


def test_the_frame_offset_is_honoured_while_it_is_set():
    """The reset must not break the case the offset exists for."""
    real_input.set_frame_origin({"x": 0.0, "y": 100.0, "w": 1440, "h": 900,
                                 "fx": 40.0, "fy": 60.0})
    try:
        sb = _Sb({"x": 100.0, "y": 100.0, "w": 180.0, "h": 48.0})
        point = real_input.screen_point(sb, object())
        assert point is not None
        # Frame offset included once, not twice: the hit test gets document
        # coordinates and the mouse gets screen ones.
        doc_x, doc_y = sb.hit_points[-1]
        assert point == (int(0.0 + 40.0 + doc_x), int(100.0 + 60.0 + doc_y))
    finally:
        real_input.reset_for_new_session()


def test_the_screen_origin_is_added_to_the_document_point():
    """The hit test wants document coordinates; the mouse wants screen ones."""
    origin = dict(VIEWPORT, x=50.0, y=200.0)
    point, sb = _aim({"x": 600.0, "y": 400.0, "w": 180.0, "h": 48.0}, origin=origin)
    doc_x, doc_y = sb.hit_points[-1]
    assert point == (int(50.0 + doc_x), int(200.0 + doc_y))
