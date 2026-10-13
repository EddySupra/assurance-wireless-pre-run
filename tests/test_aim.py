import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot import real_input  # noqa: E402

VIEWPORT = {"x": 0.0, "y": 100.0, "w": 1440, "h": 900, "fx": 0.0, "fy": 0.0}


class _Sb:
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
    assert 600 <= x <= 780
    assert 500 <= y <= 548


def test_an_element_hanging_below_the_fold_is_still_aimed_at():
    point, _ = _aim({"x": 600.0, "y": 850.0, "w": 180.0, "h": 200.0})
    assert point is not None


def test_an_element_starting_above_the_fold_is_still_aimed_at():
    point, _ = _aim({"x": 600.0, "y": -120.0, "w": 180.0, "h": 260.0})
    assert point is not None


def test_the_aim_lands_in_the_visible_part_not_the_hidden_part():
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
    point, _ = _aim({"x": 600.0, "y": 898.0, "w": 180.0, "h": 48.0})
    assert point is None


def test_an_element_with_no_size_is_refused():
    assert _aim({"x": 10.0, "y": 10.0, "w": 0.0, "h": 0.0})[0] is None


def test_something_covering_the_target_is_refused():
    point, _ = _aim({"x": 600.0, "y": 400.0, "w": 180.0, "h": 48.0}, hit=False)
    assert point is None


def test_state_from_the_last_browser_does_not_survive_into_the_next():
    real_input.set_frame_origin({"x": 0.0, "y": 0.0, "w": 800, "h": 600,
                                 "fx": 500.0, "fy": 400.0})
    real_input.reset_for_new_session()

    sb = _Sb({"x": 600.0, "y": 400.0, "w": 180.0, "h": 48.0})
    point = real_input.screen_point(sb, object())
    assert point is not None, "a fresh session must not inherit a frame offset"


def test_the_frame_offset_is_honoured_while_it_is_set():
    real_input.set_frame_origin({"x": 0.0, "y": 100.0, "w": 1440, "h": 900,
                                 "fx": 40.0, "fy": 60.0})
    try:
        sb = _Sb({"x": 100.0, "y": 100.0, "w": 180.0, "h": 48.0})
        point = real_input.screen_point(sb, object())
        assert point is not None
        doc_x, doc_y = sb.hit_points[-1]
        assert point == (int(0.0 + 40.0 + doc_x), int(100.0 + 60.0 + doc_y))
    finally:
        real_input.reset_for_new_session()


def test_the_screen_origin_is_added_to_the_document_point():
    origin = dict(VIEWPORT, x=50.0, y=200.0)
    point, sb = _aim({"x": 600.0, "y": 400.0, "w": 180.0, "h": 48.0}, origin=origin)
    doc_x, doc_y = sb.hit_points[-1]
    assert point == (int(50.0 + doc_x), int(200.0 + doc_y))
