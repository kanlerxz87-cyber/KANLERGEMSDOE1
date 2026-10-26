import hashlib
import io
from pathlib import Path
import sys
import tarfile
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from restore_template import restore

REV='a'*40
TOP='GEMSDOE32-'+REV


def archive(path, entries):
    with tarfile.open(path,'w:gz') as tar:
        for name, payload, link in entries:
            item=tarfile.TarInfo(name)
            if link:
                item.type=tarfile.SYMTYPE; item.linkname=link; tar.addfile(item)
            else:
                item.mode=0o644; item.size=len(payload); tar.addfile(item,io.BytesIO(payload))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_restore_resets_modified_and_extra_files(tmp_path):
    source=tmp_path/'template.tar.gz'
    digest=archive(source,[(TOP+'/src/holdout.py',b'original',None)])
    cache=tmp_path/'cache'; dest=restore(source,cache,REV,digest)
    (dest/'src/holdout.py').write_bytes(b'modified')
    (dest/'src/injected.py').write_text('bad')
    restore(source,cache,REV,digest)
    assert (dest/'src/holdout.py').read_bytes()==b'original'
    assert not (dest/'src/injected.py').exists()
    assert (dest/'.verified-archive-sha256').read_text().strip()==digest


@pytest.mark.parametrize('name,link',[(TOP+'/../../escape',None),(TOP+'/src/link','../../escape'),('/absolute',None)])
def test_restore_rejects_unsafe_archives(tmp_path,name,link):
    source=tmp_path/'bad.tar.gz'; digest=archive(source,[(name,b'bad',link)])
    cache=tmp_path/'cache'
    with pytest.raises(ValueError,match='unsafe archive entry'):
        restore(source,cache,REV,digest)
    assert not (tmp_path/'escape').exists()


def test_restore_rejects_wrong_archive_hash(tmp_path):
    source=tmp_path/'bad.tar.gz'; archive(source,[(TOP+'/f',b'data',None)])
    with pytest.raises(ValueError,match='hash mismatch'):
        restore(source,tmp_path/'cache',REV,'0'*64)
