#!/usr/bin/env python3
"""Prepare a separate pinned deployment package; never change production or the old package."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

old, dest, target = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3]
repo = Path(__file__).resolve().parents[2]
assert len(target)==40 and all(c in '0123456789abcdef' for c in target)
assert not dest.exists(), 'Use a new package directory'
os.umask(0o077)
def git(*args):
    return subprocess.check_output(['git','-C',str(repo),*args])
assert git('rev-parse',target).decode().strip()==target
git('merge-base','--is-ancestor','b1de1f5c487e9e074561f707045544d74b0da672',target)
for name, digest in json.loads((old/'checksums.private.json').read_text()).items():
    assert hashlib.sha256((old/name).read_bytes()).hexdigest()==digest, name
dest.mkdir(mode=0o700)
for item in old.iterdir():
    if item.is_file() and item.name not in ('deploy.lock',): shutil.copy2(item,dest/item.name)
for name in ('original','untracked','private-config','systemd-before'):
    shutil.copytree(old/name,dest/name)
manifest=json.loads((old/'manifest.private.json').read_text())
# Retain the v3 compatibility collector already running after rollback.
production=Path('/home/daniel/homelab-portal')
compat=(production/'network_archive.py').read_bytes()
assert compat==(old/'ssh-run-20261113T134834Z-6lYMtAwy/compat-network_archive.py').read_bytes()
manifest['modified_files'].append('network_archive.py')
(dest/'original/network_archive.py').write_bytes(compat)
manifest['target_commit']=target
state=Path(manifest['state_file'])
if state.exists(): manifest['state_sha256']=hashlib.sha256(state.read_bytes()).hexdigest()
(dest/'manifest.private.json').write_text(json.dumps(manifest,indent=2)+'\n')
base='10875361198982d2135bc168ca686e929460addf'
def diff(name,a,b):
    return ''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
rollback=''; forward=''
with tempfile.TemporaryDirectory() as tmp:
    tmp=Path(tmp)
    for name in manifest['modified_files']:
        original=(dest/'original'/name).read_text()
        rollback+=diff(name,git('show',base+':'+name).decode(),original)
        upstream=git('show',target+':'+name).decode()
        if name=='network_archive.py':
            assert upstream.encode()==compat
            continue
        # Both sides retain PR30 behavior; normalize its updated cache key before a three-way merge.
        ancestor=git('show','b1de1f5:'+name).decode().replace('endpoint-b-discovery','network-quality-layout')
        local=(old/'ssh-run-20261113T134834Z-6lYMtAwy/stage'/name).read_text().replace('endpoint-b-discovery','network-quality-layout')
        for key,text in [('new',upstream),('base',ancestor),('local',local)]: (tmp/key).write_text(text)
        merged=subprocess.check_output(['git','merge-file','-p',str(tmp/'new'),str(tmp/'base'),str(tmp/'local')]).decode()
        forward+=diff(name,upstream,merged)
(dest/'production.patch').write_text(rollback)
(dest/'production-on-pr30.patch').write_text(forward)
names=json.loads((old/'target-tree.sha256.json').read_text()).keys()
(dest/'target-tree.sha256.json').write_text(json.dumps({n:hashlib.sha256(git('show',target+':'+n)).hexdigest() for n in names},indent=2))
for name in ('deploy-ssh.sh','deploy-support.py','accept-live.cjs','sample-evidence.cjs'):
    shutil.copy2(Path(__file__).parent/name,dest/name)
checks=json.loads((old/'checksums.private.json').read_text())
for name in list(checks): checks[name]=hashlib.sha256((dest/name).read_bytes()).hexdigest()
checks['original/network_archive.py']=hashlib.sha256(compat).hexdigest()
(dest/'checksums.private.json').write_text(json.dumps(checks,indent=2)+'\n')
assets=['deploy-ssh.sh','deploy-support.py','accept-live.cjs','sample-evidence.cjs']
(dest/'execution-assets.sha256').write_text(''.join(hashlib.sha256((dest/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in assets))
(dest/'run.sh').write_text('#!/bin/bash\nset -euo pipefail\nexport PORTAL_DEPLOY_PACKAGE='+str(dest)+'\nexport PORTAL_DEPLOY_TARGET='+target+'\nexec bash "$PORTAL_DEPLOY_PACKAGE/deploy-ssh.sh"\n')
for path in dest.rglob('*'):
    path.chmod(0o700 if path.is_dir() else 0o600)
print(dest/'run.sh')
