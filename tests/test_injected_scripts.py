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
    for module in MODULES:
        for name in dir(module):
            if not name.endswith("_JS"):
                continue
            body = getattr(module, name)
            if isinstance(body, str) and body.strip():
                yield f"{module.__name__}.{name}", body


def test_there_are_scripts_to_check():
    found = list(_scripts())
    assert len(found) >= 8, [name for name, _ in found]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("name,body", list(_scripts()), ids=lambda v: v if isinstance(v, str) and "." in v else "")
def test_each_injected_script_parses(name, body):
    wrapped = "(function(){\n" + body + "\n});"
    proc = subprocess.run(
        [NODE, "--check", "-"], input=wrapped, capture_output=True, text=True
    )
    assert proc.returncode == 0, f"{name} does not parse:\n{proc.stderr}"


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("name,body", list(_scripts()), ids=lambda v: v if isinstance(v, str) and "." in v else "")
def test_each_injected_script_runs(name, body):
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
