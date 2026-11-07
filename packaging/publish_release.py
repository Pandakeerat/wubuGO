"""Publish already verified release staging with the native Actions GITHUB_TOKEN.

Only manually dispatched main builds may call this script. The workflow grants
contents:write to its publisher job alone. No PAT or repository secret is needed.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def run(args, *, capture=False):
    result = subprocess.run(args, check=True, text=True, capture_output=capture, timeout=180)
    return result.stdout.strip() if capture else None


def publish(staging, *, repository, tag, source_commit, root):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_EVENT_NAME') != 'workflow_dispatch' \
            or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise ValueError('Publishing requires an explicit manual Actions run on main')
    if repository != os.environ.get('GITHUB_REPOSITORY') or source_commit != os.environ.get('GITHUB_SHA'):
        raise ValueError('Publisher source/repository differs from this Actions run')
    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-rc\.\d+)?', tag) or not re.fullmatch(r'[0-9a-f]{40,64}', source_commit):
        raise ValueError('Invalid release tag or source commit')
    staging, root = Path(staging).resolve(), Path(root).resolve()
    os.chdir(root)
    release = json.loads(run(['gh', 'release', 'view', tag, '--repo', repository,
                              '--json', 'isDraft,tagName'], capture=True))
    if release.get('isDraft') is not True or release.get('tagName') != tag:
        raise ValueError('Only the existing draft release may be published; published releases are immutable here')
    if run(['git', 'status', '--porcelain', '--untracked-files=no'], capture=True):
        raise ValueError('Publisher requires a clean checkout')
    if run(['git', 'rev-parse', 'HEAD'], capture=True) != source_commit:
        raise ValueError('Checkout differs from the compiled source commit')
    run(['git', 'fetch', 'origin', 'main', '--tags'])
    if run(['git', 'rev-parse', 'origin/main'], capture=True) != source_commit:
        raise ValueError('Main advanced during the build; rerun against current main before publishing')
    tags = run(['git', 'ls-remote', '--tags', 'origin', 'refs/tags/' + tag, 'refs/tags/' + tag + '^{}'], capture=True)
    if tags:
        refs = dict(line.split()[::-1] for line in tags.splitlines())
        commit = refs.get('refs/tags/' + tag + '^{}', refs.get('refs/tags/' + tag))
        if commit != source_commit:
            raise ValueError('Release tag already refers to another commit; refusing to move it')
    files = sorted(p for p in staging.iterdir() if p.is_file() and p.name != 'release-notes.md')
    if not files or not (staging / 'SHA256SUMS').is_file():
        raise ValueError('No verified release staging files')
    run(['gh', 'release', 'upload', tag, *map(str, files), '--repo', repository, '--clobber'])
    # Publish the feed only after every asset is uploaded to the draft. A normal
    # fast-forward push rejects concurrent main updates before the release is public.
    feed = root / 'releases/update-manifest.json'
    feed.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(staging / 'update-manifest.json', feed)
    run(['git', 'config', 'user.name', 'github-actions[bot]'])
    run(['git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com'])
    run(['git', 'add', '--', 'releases/update-manifest.json'])
    changed = run(['git', 'diff', '--cached', '--name-only'], capture=True)
    if changed and changed != 'releases/update-manifest.json':
        raise ValueError('Only the generated release feed may be committed by the publisher')
    if changed:
        run(['git', 'commit', '-m', 'Update verified native release feed for ' + tag])
        run(['git', 'push', 'origin', 'HEAD:refs/heads/main'])
    run(['gh', 'release', 'edit', tag, '--repo', repository, '--draft=false', '--prerelease',
         '--target', source_commit, '--title', 'wubuGO ' + tag + ' development candidate',
         '--notes-file', str(staging / 'release-notes.md')])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('staging', 'repository', 'tag', 'source-commit'):
        parser.add_argument('--' + name, required=True)
    args = vars(parser.parse_args())
    publish(args.pop('staging'), root=Path(__file__).resolve().parents[1], **args)


if __name__ == '__main__':
    main()
