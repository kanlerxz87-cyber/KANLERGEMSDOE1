#!/usr/bin/env python3
"""Safely reinstall only regular files/dirs from the SHA-pinned public archive."""
from __future__ import annotations
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import tempfile


def restore(archive: Path, cache: Path, rev: str, expected_sha: str) -> Path:
    if len(rev) != 40 or any(c not in '0123456789abcdef' for c in rev):
        raise ValueError('invalid pinned revision')
    h = hashlib.sha256()
    with archive.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    if h.hexdigest() != expected_sha:
        raise ValueError('template archive hash mismatch')
    top = 'GEMSDOE32-' + rev
    dest = cache / top
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.template-extract-', dir=cache) as temp:
        temp_path = Path(temp)
        with tarfile.open(archive, 'r:gz') as tar:
            for member in tar:
                name = PurePosixPath(member.name)
                if (name.is_absolute() or not name.parts or name.parts[0] != top
                        or '..' in name.parts or not (member.isdir() or member.isfile())):
                    raise ValueError(f'unsafe archive entry: {member.name}')
                target = temp_path.joinpath(*name.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = tar.extractfile(member)
                    if source is None:
                        raise ValueError(f'unreadable archive entry: {member.name}')
                    with source, target.open('wb') as f:
                        shutil.copyfileobj(source, f)
                    target.chmod(member.mode & 0o755)
        extracted = temp_path / top
        if not extracted.is_dir():
            raise ValueError('archive is missing its pinned root')
        (extracted / '.verified-archive-sha256').write_text(expected_sha + '\n')
        # Only the named ignored cache entry is replaced; never touch the repo root.
        if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
            dest.unlink()
        elif dest.exists():
            shutil.rmtree(dest)
        extracted.rename(dest)
    return dest


if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise SystemExit('usage: restore_template.py ARCHIVE CACHE REV SHA256')
    restore(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4])
