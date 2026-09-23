"""Every script this project injects has to at least parse.

These modules are mostly JavaScript held in Python strings, and every test
that drives a handler stubs `execute_script` -- so a broken script passes the
whole suite and fails only against the live site, on a lead.

That is not hypothetical. Two were shipped in one edit:

    let text = ...;        // inserted
    const text = ...;      // already there

a redeclaration, which is a SyntaxError that would have killed the
qualifying-programme screen outright; and `text: text.slice(0, 160)` in a
script where nothing declared `text`, a ReferenceError at the moment a
certification was being read.

`node --check` catches the first class. The second needs the script actually
run, so each one is executed here against a small DOM stub -- not to check
what it returns, only that it can run at all.

    python -m pytest tests -q
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot import page_utils  # noqa: E402
from aw_bot.steps import step_10_classify as step10  # noqa: E402

NODE = shutil.which("node")

MODULES = (step10, page_utils)


def _scripts():
    """Every `_*_JS` constant in the modules that inject them."""
    for module in MODULES:
        for name in dir(module):
            if not name.endswith("_JS"):
                continue
            body = getattr(module, name)
            if isinstance(body, str) and body.strip():
                yield f"{module.__name__}.{name}", body


def test_there_are_scripts_to_check():
    """A rename that emptied this would otherwise make the suite pass loudly."""
    found = list(_scripts())
    assert len(found) >= 8, [name for name, _ in found]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("name,body", list(_scripts()), ids=lambda v: v if isinstance(v, str) and "." in v else "")
def test_each_injected_script_parses(name, body):
    """Wrapped the way the browser runs it: a function body, with `arguments`."""
    wrapped = "(function(){\n" + body + "\n});"
    proc = subprocess.run(
        [NODE, "--check", "-"], input=wrapped, capture_output=True, text=True
    )
    assert proc.returncode == 0, f"{name} does not parse:\n{proc.stderr}"


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("name,body", list(_scripts()), ids=lambda v: v if isinstance(v, str) and "." in v else "")
def test_each_injected_script_runs(name, body):
    """Against a stub DOM that answers everything with an empty result.

    This is not asserting what a script returns -- that depends on a real
    page. It is asserting the script can be entered at all: an identifier
    that nothing declares, a call on a missing global, or a typo in a
    property chain shows up here rather than on a lead.
    """
    harness = r"""
const el = new Proxy(function(){}, {
  get(_, k) {
    if (k === 'classList') return {contains: () => false, add(){}, remove(){}};
    if (k === 'style') return {};
    if (k === 'innerText' || k === 'value' || k === 'textContent') return '';
    if (k === 'checked' || k === 'disabled' || k === 'required') return false;
    if (k === 'id' || k === 'name') return '';
    if (k === 'length') return 0;
    if (k === Symbol.iterator) return [][Symbol.iterator].bind([]);
    if (k === 'getClientRects') return () => [];
    if (k === 'getAttribute') return () => null;
    if (k === 'querySelectorAll') return () => [];
    if (k === 'querySelector') return () => null;
    if (k === 'closest') return () => null;
    if (k === 'getBoundingClientRect') return () => ({top:0,left:0,width:0,height:0,bottom:0,right:0});
    return el;
  },
  apply() { return el; },
});
globalThis.document = new Proxy({}, {get(_, k) {
  if (k === 'querySelectorAll') return () => [];
  if (k === 'querySelector') return () => null;
  if (k === 'getElementById') return () => null;
  if (k === 'hasFocus') return () => true;
  if (k === 'title' || k === 'readyState') return '';
  if (k === 'body' || k === 'documentElement') return el;
  return el;
}});
globalThis.window = new Proxy({}, {get(_, k) {
  if (k === 'getComputedStyle') return () => new Proxy({}, {get: () => ''});
  if (k === 'innerWidth' || k === 'innerHeight' || k === 'scrollX' || k === 'scrollY') return 0;
  if (k === 'location') return {href: '', origin: ''};
  return el;
}});
globalThis.navigator = new Proxy({}, {get: () => ''});
globalThis.getComputedStyle = () => new Proxy({}, {get: () => ''});
globalThis.performance = {now: () => 0, getEntriesByType: () => []};
"""
    runner = (
        harness
        + "\nconst __fn = function(){\n" + body + "\n};\n"
        + "try { __fn('', [], '', '', ''); } catch (e) {\n"
        + "  if (e instanceof ReferenceError || e instanceof SyntaxError) {\n"
        + "    console.error(e.name + ': ' + e.message); process.exit(3);\n"
        + "  }\n"
        + "}\n"
    )
    proc = subprocess.run(
        [NODE, "--input-type=module", "-e", runner], capture_output=True, text=True
    )
    assert proc.returncode != 3, f"{name} could not run:\n{proc.stderr}"
