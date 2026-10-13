import re
import shutil
import zipfile
from pathlib import Path

from .logs import LOG

UNPACKED = ".unpacked"

_REFUSED = ("_metadata", "__MACOSX")

_DEPTH = 2

CAPSOLVER_CONFIG = Path("assets") / "config.js"
_API_KEY = re.compile(r"""(\bapiKey\s*:\s*)(['"])[^'"]*\2""")


def discover(folder: Path) -> tuple[Path, ...]:
    if not folder.is_dir():
        return ()
    found = []
    for entry in sorted(folder.iterdir()):
        if entry.name.startswith((".", "_")):
            continue
        if entry.is_dir():
            source = entry
        elif entry.suffix.lower() in (".zip", ".crx"):
            source = _unpack(entry, folder / UNPACKED / entry.stem)
        else:
            continue
        root = _manifest_dir(source)
        if root is None:
            LOG.warning(
                "Skipping %s: there is no manifest.json in it or up to two "
                "folders down, so it is not a Chrome extension.", entry,
            )
            continue
        _drop_refused(root)
        found.append(root)
    return tuple(found)


def with_capsolver_key(root: Path, key: str, scratch: Path) -> Path:
    config = root / CAPSOLVER_CONFIG
    if not key or not config.is_file():
        return root
    if "useCapsolver" not in config.read_text(encoding="utf-8"):
        return root
    if not root.is_relative_to(scratch):
        copy = scratch / f"{root.parent.name}-{root.name}"
        shutil.rmtree(copy, ignore_errors=True)
        shutil.copytree(root, copy)
        root, config = copy, copy / CAPSOLVER_CONFIG
    text = config.read_bytes().decode("utf-8")
    keyed, found = _API_KEY.subn(lambda m: f"{m[1]}{m[2]}{key}{m[2]}", text, count=1)
    keyed = keyed.replace("\r", "")
    if not found:
        LOG.warning(
            "CAPSOLVER_API_KEY is set, but %s has no apiKey line to put it "
            "in -- enter the key in the extension's popup instead.", config,
        )
    elif keyed != text:
        config.write_bytes(keyed.encode("utf-8"))
        LOG.info("Put CAPSOLVER_API_KEY from .env into %s.", config)
    return root


def _unpack(archive: Path, dest: Path) -> Path:
    stamp = dest.with_name(dest.name + ".stamp")
    stat = archive.stat()
    signature = f"{stat.st_size}:{stat.st_mtime_ns}"
    if dest.is_dir() and stamp.is_file() and stamp.read_text() == signature:
        return dest
    shutil.rmtree(dest, ignore_errors=True)
    try:
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    except zipfile.BadZipFile:
        LOG.warning("Could not unpack %s: it is not a valid .zip or .crx.", archive)
        return dest
    stamp.write_text(signature)
    return dest


def _manifest_dir(folder: Path, depth: int = _DEPTH) -> Path | None:
    if not folder.is_dir():
        return None
    if (folder / "manifest.json").is_file():
        return folder
    if depth == 0:
        return None
    inner = [found for d in folder.iterdir() if (found := _manifest_dir(d, depth - 1))]
    return max(inner, key=lambda d: d.stat().st_mtime) if inner else None


def _drop_refused(root: Path) -> None:
    for name in _REFUSED:
        path = root / name
        if path.is_dir():
            shutil.rmtree(path)
            LOG.info(
                "Removed %s from %s: Chrome will not load an unpacked "
                "extension that has it.", name, root,
            )
