#!/usr/bin/env python3
"""Prepare immutable public-releases artifacts; never upload or release them."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tempfile

REPOSITORY = "ymasaki/public-releases"
MAX_SIZE = 512 << 20


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def metadata(info, architectures, size, digest, notes):
    if info.get("DevBoardSourceRepo"):
        raise ValueError("Remove private DevBoardSourceRepo before distribution signing")
    app_id = info["CFBundleIdentifier"]
    version = info["CFBundleShortVersionString"]
    build = int(info["CFBundleVersion"])
    commit = info["DevBoardCommit"]
    minimum = info["LSMinimumSystemVersion"]
    if not re.fullmatch(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*", app_id):
        raise ValueError("Invalid bundle identifier")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) or build <= 0:
        raise ValueError("Expected semantic version and positive monotonic build")
    if not re.fullmatch(r"[a-fA-F0-9]{40}", commit):
        raise ValueError("DevBoardCommit must be the full source revision (40 hex digits)")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,2}", minimum):
        raise ValueError("Invalid minimum macOS version")
    if not architectures or not set(architectures) <= {"arm64", "x86_64"}:
        raise ValueError("Unsupported architecture")
    if not 0 < size <= MAX_SIZE or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Invalid artifact size/hash")
    if len(notes) > 100 or any(len(line) > 2000 for line in notes):
        raise ValueError("Release notes too large")
    tag = f"{app_id}-{version}-{build}"
    filename = f"{tag}.zip"
    release = dict(schemaVersion=1, appID=app_id, channel="stable", version=version,
                   build=build, commit=commit, notes=notes, minimumSystemVersion=minimum,
                   architectures=architectures,
                   asset=dict(url=f"https://github.com/{REPOSITORY}/releases/download/{tag}/{filename}",
                              size=size, sha256=digest))
    data = manifest_bytes(release)
    return release, filename, data


def manifest_bytes(release):
    data = (json.dumps(release, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(data) > 64 << 10:
        raise ValueError("Manifest exceeds 64 KiB")
    return data


def prepare(app, destination, notes):
    app = app.resolve()
    destination = destination.resolve()
    if destination == app or app in destination.parents:
        raise ValueError("Output must be outside the input app")
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    # This is the public Internet distribution boundary, stricter than the
    # existing same-Team peer receiver which also accepts Apple Development.
    run("/usr/bin/codesign", "--verify", "--deep", "--strict", str(app))
    signing = subprocess.run(["/usr/bin/codesign", "-dv", "--verbose=4", str(app)],
                             check=True, capture_output=True, text=True).stderr
    if "Authority=Developer ID Application:" not in signing:
        raise ValueError("Public releases require Developer ID Application signing")
    run("/usr/sbin/spctl", "--assess", "--type", "execute", str(app))
    run("/usr/bin/xcrun", "stapler", "validate", str(app))
    executable = app / "Contents/MacOS" / info["CFBundleExecutable"]
    architectures = run("/usr/bin/lipo", "-archs", str(executable)).split()
    # Reject archives the receiver would refuse: no symbolic links, only the
    # .app root, bounded expansion and member count. ditto excludes resource forks.
    paths = [app] + list(app.rglob("*"))
    if any(path.is_symlink() or (not path.is_file() and not path.is_dir()) for path in paths):
        raise ValueError("Artifact contains links or special files")
    if len(paths) > 20_000 or sum(p.stat().st_size for p in paths if p.is_file()) > 2 << 30:
        raise ValueError("Artifact exceeds receiver expansion limits")
    # Work outside the source app and refuse to overwrite a prior output.
    if destination.exists():
        raise ValueError("Output already exists; release artifacts are immutable")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="public-release-", dir=destination.parent) as temp:
        directory = Path(temp)
        archive = directory / "artifact.zip"
        run("/usr/bin/ditto", "-c", "-k", "--norsrc", "--keepParent", str(app), str(archive))
        hash_value = hashlib.sha256()
        with archive.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                hash_value.update(chunk)
        digest = hash_value.hexdigest()
        release, filename, data = metadata(info, architectures, archive.stat().st_size, digest, notes)
        archive.rename(directory / filename)
        (directory / "stable.json").write_bytes(data)
        shutil.copytree(directory, destination)
    print(destination)
    print(f"Tag: {release['appID']}-{release['version']}-{release['build']}")
    print("Prepared locally. Nothing has been uploaded or published.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    parser.add_argument("output", type=Path, help="New local directory (must not exist)")
    parser.add_argument("--notes", type=Path, help="UTF-8 file; one change per line")
    args = parser.parse_args()
    notes = [line for line in args.notes.read_text().splitlines() if line.strip()] if args.notes else []
    try:
        prepare(args.app, args.output, notes)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"prepare-public-release: {error}\n")


if __name__ == "__main__":
    main()
