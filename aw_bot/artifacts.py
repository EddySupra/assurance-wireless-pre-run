"""Per-step evidence: screenshot, saved HTML, and an inventory of the
interactive elements actually on the page.

The inventory is the useful one while we build page by page -- it tells us the
real ids/names/labels to target on the next page instead of guessing.
"""

import json
from pathlib import Path

from .logs import LOG

# Pulls every control a form step could care about, with the attributes we'd
# use to build a selector. Trimmed to visible elements only.
_INVENTORY_JS = r"""
const visible = (el) => {
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return false;
  const s = window.getComputedStyle(el);
  return s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
};
const clean = (t) => (t || '').replace(/\s+/g, ' ').trim().slice(0, 120);
const grab = (el) => ({
  tag: el.tagName.toLowerCase(),
  type: el.getAttribute('type') || null,
  id: el.id || null,
  name: el.getAttribute('name') || null,
  placeholder: el.getAttribute('placeholder') || null,
  aria: el.getAttribute('aria-label') || null,
  href: el.getAttribute('href') || null,
  testid: el.getAttribute('data-testid') || null,
  cls: clean(el.getAttribute('class')),
  text: clean(el.innerText || el.value),
});
const out = {inputs: [], selects: [], buttons: [], links: [], iframes: []};
document.querySelectorAll('input, textarea').forEach((el) => {
  if (visible(el)) out.inputs.push(grab(el));
});
document.querySelectorAll('select').forEach((el) => {
  if (visible(el)) out.selects.push(grab(el));
});
document.querySelectorAll('button, [role=button], input[type=submit]').forEach((el) => {
  if (visible(el)) out.buttons.push(grab(el));
});
document.querySelectorAll('a[href]').forEach((el) => {
  if (visible(el) && clean(el.innerText)) out.links.push(grab(el));
});
document.querySelectorAll('iframe').forEach((el) => {
  out.iframes.push({src: el.getAttribute('src'), id: el.id || null, title: el.getAttribute('title')});
});
return out;
"""


def capture(sb, run_dir: Path, step_name: str, save: bool = True) -> dict:
    """Screenshot + HTML + element inventory for one step. Never fatal."""
    inventory = {}
    if not save:
        return inventory

    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        sb.save_screenshot(f"{step_name}.png", folder=str(run_dir))
    except Exception as exc:  # a missing screenshot must not fail the run
        LOG.warning("Screenshot failed for %s: %s", step_name, exc)

    try:
        (run_dir / f"{step_name}.html").write_text(sb.get_page_source(), encoding="utf-8")
    except Exception as exc:
        LOG.warning("HTML dump failed for %s: %s", step_name, exc)

    try:
        inventory = sb.execute_script(_INVENTORY_JS) or {}
        (run_dir / f"{step_name}_elements.json").write_text(
            json.dumps(inventory, indent=2), encoding="utf-8"
        )
        LOG.info(
            "Page inventory: %d inputs, %d selects, %d buttons, %d links, %d iframes",
            len(inventory.get("inputs", [])),
            len(inventory.get("selects", [])),
            len(inventory.get("buttons", [])),
            len(inventory.get("links", [])),
            len(inventory.get("iframes", [])),
        )
    except Exception as exc:
        LOG.warning("Element inventory failed for %s: %s", step_name, exc)

    LOG.info("Artifacts saved to %s", run_dir)
    return inventory
