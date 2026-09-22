"""Controls below the fold must still be reachable by the real cursor.

The failure this pins was quiet and expensive: `screen_point` bounds-checked
the element's top-left corner, so anything whose top sat outside the viewport
was refused -- and every refusal fell back to setting the control by script.
Two of five dropdowns on one lead were driven properly and the rest were
assigned, which is the opposite of what --real-input is for.

    python -m pytest tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot import real_input  # noqa: E402

VIEWPORT = {"x": 0.0, "y": 100.0, "w": 1440, "h": 900, "fx": 0.0, "fy": 0.0}


class _Sb:
    def __init__(self, box, origin=None, hit=True):
        self.box = box
        self.origin = dict(origin or VIEWPORT)
        self.hit = hit
        self.hit_points = []

    def execute_script(self, script, *args):
        if "getBoundingClientRect" in script:
            return dict(self.box)
        if "elementFromPoint" in script:
            self.hit_points.append((args[1], args[2]))
            return {"hit": self.hit, "what": "div.wrapper"}
        return dict(self.origin)


def _aim(box, **kw):
    real_input.set_frame_origin(None)
    sb = _Sb(box, **kw)
    return real_input.screen_point(sb, object()), sb


def test_a_dropdown_low_on_the_page_is_reachable():
    """`#securityQuestion0` sits near the bottom and was being refused."""
    point, _ = _aim({"x": 310.0, "y": 860.0, "w": 300.0, "h": 38.0})
    assert point is not None


def test_a_control_straddling_the_fold_is_reachable():
    point, _ = _aim({"x": 310.0, "y": 880.0, "w": 300.0, "h": 120.0})
    assert point is not None


def test_a_control_scrolled_above_the_fold_is_reachable():
    point, _ = _aim({"x": 310.0, "y": -60.0, "w": 300.0, "h": 200.0})
    assert point is not None


def test_the_aim_stays_inside_the_viewport():
    """Aiming at the true centre of a half-visible control misses the screen."""
    box = {"x": 310.0, "y": -300.0, "w": 300.0, "h": 400.0}
    for _ in range(30):
        point, sb = _aim(box)
        assert point is not None
        doc_y = sb.hit_points[-1][1]
        assert 0.0 <= doc_y <= 100.0, doc_y


def test_something_genuinely_off_screen_is_still_refused():
    """The check has to keep working, not just say yes to everything."""
    assert _aim({"x": 310.0, "y": 2000.0, "w": 300.0, "h": 38.0})[0] is None


def test_a_covered_control_is_still_refused():
    point, _ = _aim({"x": 310.0, "y": 400.0, "w": 300.0, "h": 38.0}, hit=False)
    assert point is None


def test_the_wheel_is_aimed_before_it_is_turned():
    """Otherwise the scroll lands on whatever the cursor happens to be over.

    Inside the enrollment frame that is usually the outer page, which moves
    the frame and invalidates the offset every later click is aimed with.
    """
    import inspect

    source = inspect.getsource(real_input.scroll_to)
    assert "_park_pointer_over_document" in source
