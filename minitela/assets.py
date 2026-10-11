"""Factory GIFs, imported from the official .deb that the user downloaded.

They are not redistributed with this project. Each factory GIF comes as a preview
(`gifs_imagens/N.gif`) and as a ready-made texture for the device (`ACF/TextureN.acf`):
the whole AHMI layout with that GIF on the Gif1 page.
"""

import hashlib
import io
import json
import re
import tarfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO

from minitela.paths import data_dir

_RESOURCES = "usr/share/minitela/resources/"
_TEXTURE = re.compile(rf"^(?:\./)?{_RESOURCES}ACF/Texture(\d+)\.acf$")
_PREVIEW = re.compile(rf"^(?:\./)?{_RESOURCES}gifs_imagens/(\d+)\.gif$")

_AR_MAGIC = b"!<arch>\n"
_AR_HEADER = 60


class InvalidPackageError(ValueError):
    """The file is not the official minitela .deb."""


@dataclass(frozen=True)
class FactoryGif:
    number: int
    texture: str  # file names, relative to the library directory
    preview: str
    md5: str  # of the texture, also the file id used when uploading it
    size: int


class _Section(io.RawIOBase):
    """Read-only window over part of a file, so a large ar member is streamed, not loaded."""

    def __init__(self, file: BinaryIO, size: int):
        self._file = file
        self._left = size

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        if self._left <= 0:
            return 0
        data = self._file.read(min(len(buffer), self._left))
        buffer[: len(data)] = data
        self._left -= len(data)
        return len(data)


def _ar_members(file: BinaryIO):
    """Yield (name, size) for each member of an ar archive, leaving `file` at its data."""
    if file.read(len(_AR_MAGIC)) != _AR_MAGIC:
        raise InvalidPackageError("not a .deb package")
    while header := file.read(_AR_HEADER):
        if len(header) < _AR_HEADER or header[58:60] != b"`\n":
            raise InvalidPackageError("corrupted .deb package")
        name = header[:16].decode().strip().rstrip("/")
        size = int(header[48:58].decode().strip())
        start = file.tell()
        yield name, size
        file.seek(start + size + size % 2)


def _read_package(deb: Path) -> tuple[dict[int, bytes], dict[int, bytes]]:
    textures: dict[int, bytes] = {}
    previews: dict[int, bytes] = {}
    with deb.open("rb") as file:
        for name, size in _ar_members(file):
            if not name.startswith("data.tar"):
                continue
            stream = io.BufferedReader(_Section(file, size), buffer_size=1 << 20)
            with tarfile.open(fileobj=stream, mode="r|*") as tar:
                for member in tar:
                    if not member.isfile():
                        continue
                    for pattern, found in ((_TEXTURE, textures), (_PREVIEW, previews)):
                        if match := pattern.match(member.name):
                            extracted = tar.extractfile(member)
                            assert extracted is not None
                            found[int(match.group(1))] = extracted.read()
    return textures, previews


def library_dir() -> Path:
    return data_dir() / "factory"


def import_deb(deb: Path, library: Path | None = None) -> list[FactoryGif]:
    """Copy the factory GIFs out of the official package into the library directory."""
    library = library or library_dir()
    textures, previews = _read_package(deb)
    numbers = sorted(set(textures) & set(previews))
    if not numbers:
        raise InvalidPackageError(f"{deb.name} has no factory GIFs; is it the minitela package?")
    library.mkdir(parents=True, exist_ok=True)
    gifs = []
    for number in numbers:
        texture, preview = f"texture{number}.acf", f"preview{number}.gif"
        (library / texture).write_bytes(textures[number])
        (library / preview).write_bytes(previews[number])
        md5 = hashlib.md5(textures[number]).hexdigest()
        gifs.append(FactoryGif(number, texture, preview, md5, len(textures[number])))
    manifest = {"gifs": [asdict(gif) for gif in gifs]}
    (library / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return gifs


def load_library(library: Path | None = None) -> list[FactoryGif]:
    """GIFs imported earlier, or an empty list."""
    manifest = (library or library_dir()) / "manifest.json"
    if not manifest.exists():
        return []
    return [FactoryGif(**gif) for gif in json.loads(manifest.read_text())["gifs"]]
