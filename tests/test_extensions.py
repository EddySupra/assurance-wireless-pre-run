import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aw_bot.extensions import discover, with_capsolver_key  # noqa: E402

MANIFEST = '{"manifest_version": 3, "name": "t", "version": "1"}'


def _extension(folder: Path) -> Path:
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(MANIFEST)
    return folder


def _zip(path: Path, inner: str = "") -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(inner + "manifest.json", MANIFEST)
    return path


def test_a_missing_folder_loads_nothing(tmp_path):
    assert discover(tmp_path / "extensions") == ()


def test_an_unpacked_folder_loads_as_it_is(tmp_path):
    ext = _extension(tmp_path / "my-ext")
    assert discover(tmp_path) == (ext,)


def test_a_folder_one_level_down_is_found(tmp_path):
    inner = _extension(tmp_path / "my-ext" / "my-ext-1.2")
    assert discover(tmp_path) == (inner,)


def test_a_folder_two_levels_down_is_found(tmp_path):
    inner = _extension(tmp_path / "abcdefgh" / "abcdefgh" / "1.0_0")
    assert discover(tmp_path) == (inner,)


def test_a_folder_three_levels_down_is_not_found(tmp_path):
    _extension(tmp_path / "my-ext" / "a" / "b" / "c")
    assert discover(tmp_path) == ()


def test_a_copy_from_chrome_uses_the_newest_version_without_metadata(tmp_path):
    old = _extension(tmp_path / "abcdefgh" / "1.0_0")
    new = _extension(tmp_path / "abcdefgh" / "1.1_0")
    (new / "_metadata").mkdir()
    (new / "_metadata" / "verified_contents.json").write_text("{}")
    os.utime(old, (1, 1))
    assert discover(tmp_path) == (new,)
    assert not (new / "_metadata").exists()


def test_a_zip_is_unpacked_and_loaded(tmp_path):
    _zip(tmp_path / "my-ext.zip")
    (found,) = discover(tmp_path)
    assert found == tmp_path / ".unpacked" / "my-ext"
    assert (found / "manifest.json").is_file()


def test_a_zip_with_its_own_top_folder_is_found(tmp_path):
    _zip(tmp_path / "my-ext.zip", inner="my-ext/")
    assert discover(tmp_path) == (tmp_path / ".unpacked" / "my-ext" / "my-ext",)


def test_a_crx_is_unpacked_past_its_header(tmp_path):
    body = _zip(tmp_path / "body.zip").read_bytes()
    (tmp_path / "body.zip").unlink()
    (tmp_path / "my-ext.crx").write_bytes(b"Cr24\x03\x00\x00\x00" + b"\x00" * 64 + body)
    (found,) = discover(tmp_path)
    assert (found / "manifest.json").is_file()


def test_a_changed_zip_is_unpacked_again(tmp_path):
    archive = _zip(tmp_path / "my-ext.zip")
    (found,) = discover(tmp_path)
    (found / "stale.js").write_text("")
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("manifest.json", MANIFEST)
        z.writestr("fresh.js", "")
    discover(tmp_path)
    assert (found / "fresh.js").is_file() and not (found / "stale.js").exists()


CAPSOLVER = "export const defaultConfig = {\n  // API key\n  apiKey: '',\n  useCapsolver: true,\n};\n"


def _capsolver(folder: Path) -> Path:
    _extension(folder)
    (folder / "assets").mkdir()
    (folder / "assets" / "config.js").write_bytes(CAPSOLVER.encode())
    return folder


def test_the_capsolver_config_keeps_plain_newlines(tmp_path):
    scratch = tmp_path / ".unpacked"
    unpacked = _capsolver(scratch / "capsolver")
    config = unpacked / "assets" / "config.js"
    config.write_bytes(CAPSOLVER.replace("\n", "\r\n").encode())
    with_capsolver_key(unpacked, "CAP-123", scratch)
    assert b"\r" not in config.read_bytes()
    assert b"apiKey: 'CAP-123'" in config.read_bytes()


def test_the_capsolver_key_goes_into_a_copy_not_the_original(tmp_path):
    original = _capsolver(tmp_path / "abcdefgh" / "1.0_0")
    scratch = tmp_path / ".unpacked"
    loaded = with_capsolver_key(original, "CAP-123", scratch)
    assert loaded.parent == scratch
    assert "apiKey: 'CAP-123'" in (loaded / "assets" / "config.js").read_text()
    assert (original / "assets" / "config.js").read_bytes() == CAPSOLVER.encode()


def test_an_unpacked_capsolver_gets_its_key_in_place(tmp_path):
    scratch = tmp_path / ".unpacked"
    unpacked = _capsolver(scratch / "capsolver")
    assert with_capsolver_key(unpacked, "CAP-123", scratch) == unpacked
    assert "apiKey: 'CAP-123'" in (unpacked / "assets" / "config.js").read_text()
    with_capsolver_key(unpacked, "CAP-456", scratch)
    assert "apiKey: 'CAP-456'" in (unpacked / "assets" / "config.js").read_text()


def test_no_key_or_another_extension_is_left_alone(tmp_path):
    scratch = tmp_path / ".unpacked"
    capsolver = _capsolver(tmp_path / "capsolver")
    other = _extension(tmp_path / "other")
    assert with_capsolver_key(capsolver, "", scratch) == capsolver
    assert with_capsolver_key(other, "CAP-123", scratch) == other
    assert not scratch.exists()


def test_things_that_are_not_extensions_are_skipped(tmp_path):
    (tmp_path / "README.txt").write_text("drop extensions here")
    (tmp_path / "empty-folder").mkdir()
    (tmp_path / "broken.zip").write_bytes(b"not a zip")
    assert discover(tmp_path) == ()
