import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from selenium.common.exceptions import WebDriverException  # noqa: E402

from aw_bot.human import _will_receive_keys  # noqa: E402


class _Sb:
    def __init__(self, in_field, window_focused, framed):
        self.state = {
            "inField": in_field,
            "windowFocused": window_focused,
            "framed": framed,
        }
        self.reads = 0

    def execute_script(self, script, *args):
        self.reads += 1
        return dict(self.state)


def test_a_focused_field_in_the_enrollment_frame_is_accepted():
    sb = _Sb(in_field=True, window_focused=False, framed=True)
    assert _will_receive_keys(sb, object()) is True


def test_a_focused_field_at_the_top_level_needs_the_window_too():
    assert _will_receive_keys(_Sb(True, True, False), object()) is True


def test_an_unfocused_window_at_the_top_level_is_refused():
    sb = _Sb(in_field=True, window_focused=False, framed=False)
    assert _will_receive_keys(sb, object(), timeout=0.3) is False


def test_the_caret_being_elsewhere_is_always_refused():
    assert _will_receive_keys(_Sb(False, True, True), object(), timeout=0.3) is False
    assert _will_receive_keys(_Sb(False, True, False), object(), timeout=0.3) is False


def test_a_lost_element_is_refused_rather_than_waited_on():
    class Gone:
        def execute_script(self, script, *args):
            raise WebDriverException("stale element")

    assert _will_receive_keys(Gone(), object(), timeout=2.0) is False


def test_it_polls_rather_than_reading_once():
    sb = _Sb(in_field=False, window_focused=True, framed=True)
    _will_receive_keys(sb, object(), timeout=0.4)
    assert sb.reads > 1
