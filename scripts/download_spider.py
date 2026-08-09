"""Download and safely extract the officially linked Spider 1.0 archive."""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

URL = "https://drive.usercontent.google.com/download?id=1403EGqzIDoHMdQF4c9Bkyl7dZLZ5Wt6J&export=download&confirm=t"
SHA256 = "00636695dabed6b5f4b8328a16b13e069a2f16591d5efcce57660669c85b121b"
ARCHIVE = Path("data/raw/spider/spider.zip")
TARGET = Path("data/raw/spider")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    if not ARCHIVE.exists() or digest(ARCHIVE) != SHA256:
        temporary = ARCHIVE.with_suffix(".download")
        with urllib.request.urlopen(URL, timeout=300) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        if digest(temporary) != SHA256:
            temporary.unlink(missing_ok=True)
            raise RuntimeError("Spider archive checksum mismatch")
        temporary.replace(ARCHIVE)
    with zipfile.ZipFile(ARCHIVE) as archive:
        for member in archive.infolist():
            relative = PurePosixPath(member.filename)
            if relative.parts[:1] != ("spider_data",) or ".." in relative.parts:
                continue
            destination = TARGET.joinpath(*relative.parts)
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
    print(f"Spider ready: {TARGET / 'spider_data'} sha256={SHA256}")


if __name__ == "__main__":
    main()
