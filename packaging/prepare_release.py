"""Stage verified native CI outputs and generate a release feed from their bytes.

This script does not contact GitHub or publish anything. Run from the repository
checkout used by both native build jobs. Inputs are kept in separate platform
directories so same-named verification reports cannot overwrite each other.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

PAGES = {'Overview', 'Setup', 'Weapons', 'Classic UI', 'Launch', 'Downloads',
         'Settings', 'Integrity', 'Diagnostics'}


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read_object(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 2_000_000:
        raise ValueError(f'Unsafe or oversized report: {path}')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError(f'Expected JSON object: {path}')
    return value


def check_report(path, *, gui):
    report = read_object(path)
    if report.get('ok') is not True or report.get('game_started') is not False:
        raise ValueError(f'Native acceptance report failed: {path}')
    if gui and (report.get('isolated_state') is not True or report.get('network_used') is not False
                or report.get('generated_weapons') != 33 or set(report.get('pages', [])) != PAGES
                or report.get('assets', {}).get('ok') is not True
                or report.get('external_process', {}).get('loader_isolation_verified') is not True):
        raise ValueError(f'Native GUI report is incomplete: {path}')
    return report


def checksums(directory):
    records = {}
    for line in (directory / 'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9._-]+)', line)
        if not match or match[2] in records:
            raise ValueError(f'Invalid or duplicate native checksum: {line}')
        records[match[2]] = match[1]
    return records


def prepare(windows, fedora, output, *, repository, tag, version, source_commit, run_id, root):
    root = Path(root).resolve()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Expected GitHub owner/repository')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or not re.fullmatch(
            r'v' + re.escape(version) + r'(?:-rc\.\d+)?', tag):
        raise ValueError('Release tag must match the numeric app version, optionally -rc.N')
    if not re.fullmatch(r'[0-9a-f]{40,64}', source_commit) or not str(run_id).isdigit():
        raise ValueError('Expected source commit SHA and numeric Actions run ID')
    source_commit = subprocess.check_output(
        ['git', 'rev-parse', '--verify', source_commit + '^{commit}'], cwd=root, text=True).strip()
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Release staging directory must be empty')
    output.mkdir(parents=True, exist_ok=True)
    names = {
        'windows': [f'wubuGO-{version}-windows-x64-setup.exe', f'wubuGO-{version}-windows-x64-portable.zip'],
        'fedora': [f'wubuGO-{version}-linux-x64-portable.tar.gz'],
    }
    windows, fedora = Path(windows).resolve(), Path(fedora).resolve()
    rpms = sorted(fedora.glob(f'wubugo-{version}-*.x86_64.rpm'))
    if len(rpms) != 1:
        raise ValueError('Expected exactly one native Fedora RPM')
    names['fedora'].append(rpms[0].name)
    reports = {
        'windows': ['frozen-selftest.json', 'installed-selftest.json', 'installer-smoke.json'],
        'fedora': ['frozen-selftest.json', 'user-installed-selftest.json',
                   'rpm-installed-selftest.json', 'installer-smoke.json'],
    }
    evidence = {'repository': repository, 'source_commit': source_commit,
                'ci_run_url': f'https://github.com/{repository}/actions/runs/{run_id}',
                'in_game_verified': False, 'reports': {}}
    report_files = []
    for platform, directory in [('windows', windows), ('fedora', fedora)]:
        records = checksums(directory)
        for name in names[platform]:
            path = directory / name
            if path.is_symlink() or not path.is_file() or digest(path) != records.get(name):
                raise ValueError(f'Native artifact missing or checksum mismatch: {path}')
            shutil.copy2(path, output / name)
        for name in reports[platform]:
            path = directory / name
            check_report(path, gui=name != 'installer-smoke.json')
            evidence['reports'][platform + '/' + name] = {'sha256': digest(path)}
            report_files.append((path, platform + '/' + name))
        log = directory / 'installer-test.log'
        if log.is_file() and not log.is_symlink():
            report_files.append((log, platform + '/' + log.name))
    with zipfile.ZipFile(output / f'wubuGO-{version}-verification.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, name in report_files:
            archive.write(path, name)
        archive.writestr('evidence.json', json.dumps(evidence, indent=2) + '\n')
    subprocess.run(['git', 'archive', '--format=zip', '--prefix=wubuGO-' + version + '/',
                    '--output=' + str(output / f'wubuGO-{version}-source.zip'), source_commit],
                   cwd=root, check=True)
    base = f'https://github.com/{repository}/releases/download/{tag}/'
    assets = {}
    for platform, name in [('windows-x64', names['windows'][0]), ('linux-x64', names['fedora'][0])]:
        path = output / name
        assets[platform] = {'url': base + name, 'filename': name,
                            'sha256': digest(path), 'size': path.stat().st_size}
    manifest = {'version': version, 'notes': 'Windows and Fedora launcher/installer workflows passed native CI. '
                'In-game HUD, menu and weapon effects remain unverified.', 'assets': assets}
    (output / 'update-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (output / 'release-notes.md').write_text(
        f'wubuGO {tag} is a development prerelease.\n\n'
        f'- Windows: bundled runtime, portable ZIP and per-user installer.\n'
        f'- Fedora 43: bundled portable archive and RPM.\n'
        f'- Native CI passed GUI checks, offline 33-weapon generation, actual installation/uninstallation and user-state retention.\n'
        f'- [Build and verification run]({evidence["ci_run_url"]}) · source `{source_commit}`.\n\n'
        'Download SHA256SUMS and the verification ZIP for checksums and native reports. '
        'The game is installed through Steam. In-game HUD/menu and weapon effects remain unverified; '
        'native Linux Bridge/MIGI injection is unsupported. Use modified clients only in offline/private -insecure sessions.\n',
        encoding='utf-8')
    staged = sorted(p for p in output.iterdir() if p.is_file() and p.name != 'release-notes.md')
    (output / 'SHA256SUMS').write_text(''.join(f'{digest(path)}  {path.name}\n' for path in staged), encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('windows', 'fedora', 'output', 'repository', 'tag', 'source-commit', 'run-id'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--version', default='6.0.1')
    args = vars(parser.parse_args())
    root = Path(__file__).resolve().parents[1]
    prepare(args.pop('windows'), args.pop('fedora'), args.pop('output'), root=root, **args)


if __name__ == '__main__':
    main()
