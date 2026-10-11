#!/usr/bin/env python3
"""Write the Flatpak module that installs the Python packages the build needs.

flatpak-builder downloads nothing during the build, so every wheel is listed with its
URL and SHA-256 (taken from PyPI). Run again after changing the pins below:

    python3 tools/flatpak-pip-deps.py > build-aux/flatpak/python3-deps.json
"""

import json
import sys
import urllib.request

# What the app needs at run time.
RUNTIME = {"pyserial": "3.5"}
# What building the app needs (hatchling and its dependencies); removed from the final app.
BUILD = {
    "hatchling": "1.32.4",
    "packaging": "26.3",
    "pathspec": "1.1.1",
    "pluggy": "1.6.0",
    "tomlkit": "0.15.1",
    "trove-classifiers": "2026.9.21.13",
}


def wheel(name: str, version: str) -> dict:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=30) as response:
        release = json.load(response)
    for file in release["urls"]:
        if file["packagetype"] == "bdist_wheel" and file["filename"].endswith("-none-any.whl"):
            return {"type": "file", "url": file["url"], "sha256": file["digests"]["sha256"]}
    sys.exit(f"{name} {version}: no pure-Python wheel on PyPI")


def module(name: str, pins: dict[str, str]) -> dict:
    requirements = " ".join(f"{package}=={version}" for package, version in pins.items())
    return {
        "name": name,
        "buildsystem": "simple",
        "build-commands": [
            "pip3 install --verbose --exists-action=i --no-index --find-links=file://${PWD} "
            "--prefix=${FLATPAK_DEST} --no-build-isolation " + requirements
        ],
        "sources": [wheel(package, version) for package, version in pins.items()],
    }


def main() -> None:
    deps = module("python3-deps", RUNTIME)
    build = module("python3-build-deps", BUILD)
    build["cleanup"] = ["*"]  # only needed while building
    deps["modules"] = [build]
    json.dump(deps, sys.stdout, indent=4)
    print()


if __name__ == "__main__":
    main()
