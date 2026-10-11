import hashlib
import io
import tarfile

import pytest

from minitela import assets, paths
from minitela.assets import FactoryGif, InvalidPackageError, import_deb, load_library

RESOURCES = "./usr/share/minitela/resources/"


def ar_archive(members: list[tuple[str, bytes]]) -> bytes:
    out = bytearray(b"!<arch>\n")
    for name, data in members:
        header = f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(data):<10}`\n"
        out += header.encode() + data + (b"\n" if len(data) % 2 else b"")
    return bytes(out)


def tar_xz(files: dict[str, bytes | None]) -> bytes:
    """A tar.xz with the given files; None makes a directory."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:xz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            if data is None:
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
                continue
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def make_deb(path, files: dict[str, bytes | None]):
    path.write_bytes(
        ar_archive(
            [
                ("debian-binary", b"2.0\n"),
                ("control.tar.xz", tar_xz({"./control": b"Package: minitela\n"})),
                ("data.tar.xz", tar_xz(files)),
            ]
        )
    )
    return path


@pytest.fixture
def deb(tmp_path):
    return make_deb(
        tmp_path / "minitela_1.0.20_amd64.deb",
        {
            RESOURCES + "ACF/": None,
            RESOURCES + "ACF/Texture1.acf": b"texture one",
            RESOURCES + "ACF/Texture2.acf": b"texture 2",
            RESOURCES + "ACF/Texture.acf": b"current texture, no number",
            RESOURCES + "ACF/file.zip": b"zip",
            RESOURCES + "gifs_imagens/1.gif": b"GIF89a one",
            RESOURCES + "gifs_imagens/2.gif": b"GIF89a two",
            RESOURCES + "gifs_imagens/0.gif": b"preview without texture",
            "./usr/share/minitela/minitela": b"\x7fELF",
        },
    )


def test_import(deb, tmp_path):
    library = tmp_path / "library"
    gifs = import_deb(deb, library)
    assert gifs == [
        FactoryGif(1, "texture1.acf", "preview1.gif", hashlib.md5(b"texture one").hexdigest(), 11),
        FactoryGif(2, "texture2.acf", "preview2.gif", hashlib.md5(b"texture 2").hexdigest(), 9),
    ]
    assert (library / "texture1.acf").read_bytes() == b"texture one"
    assert (library / "preview2.gif").read_bytes() == b"GIF89a two"
    assert sorted(p.name for p in library.iterdir()) == [
        "manifest.json",
        "preview1.gif",
        "preview2.gif",
        "texture1.acf",
        "texture2.acf",
    ]
    assert load_library(library) == gifs


def test_paths_without_dot_prefix(tmp_path):
    deb = make_deb(
        tmp_path / "x.deb",
        {
            "usr/share/minitela/resources/ACF/Texture3.acf": b"t",
            "usr/share/minitela/resources/gifs_imagens/3.gif": b"g",
        },
    )
    assert [gif.number for gif in import_deb(deb, tmp_path / "lib")] == [3]


def test_not_a_deb(tmp_path):
    path = tmp_path / "x.deb"
    path.write_bytes(b"PK\x03\x04 zip file")
    with pytest.raises(InvalidPackageError, match=r"not a \.deb"):
        import_deb(path, tmp_path / "lib")


def test_corrupted_deb(tmp_path):
    path = tmp_path / "x.deb"
    path.write_bytes(b"!<arch>\n" + b"x" * 70)
    with pytest.raises(InvalidPackageError, match="corrupted"):
        import_deb(path, tmp_path / "lib")


def test_other_package(tmp_path):
    deb = make_deb(tmp_path / "other.deb", {"./usr/bin/other": b"x"})
    with pytest.raises(InvalidPackageError, match="no factory GIFs"):
        import_deb(deb, tmp_path / "lib")
    assert not (tmp_path / "lib").exists()


def test_empty_library(tmp_path):
    assert load_library(tmp_path / "nothing") == []


def test_default_library_follows_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert assets.library_dir() == tmp_path / "minitela" / "factory"


def test_data_dir_default(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.data_dir() == tmp_path / ".local" / "share" / "minitela"
