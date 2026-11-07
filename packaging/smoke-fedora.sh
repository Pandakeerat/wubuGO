#!/usr/bin/env bash
# Acceptance tests of the actual portable archive and RPM on disposable Fedora CI.
# No game or third-party injection tools are installed or launched.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${CI:-}" != 'true' || "$(id -u)" != '0' ]]; then
    printf '%s\n' 'Run this only in the disposable Fedora CI container as root.' >&2
    exit 1
fi
if ! grep -q '^ID=fedora$' /etc/os-release; then
    printf '%s\n' 'This acceptance script requires native Fedora.' >&2
    exit 1
fi
task_root="$PWD"
task_archive="$task_root/dist/wubuGO-6.0.1-linux-x64-portable.tar.gz"
mapfile -t task_rpms < <(find "$task_root/dist" -maxdepth 1 -name 'wubugo-*.x86_64.rpm' -type f)
if [[ ! -f "$task_archive" || "${#task_rpms[@]}" != '1' ]]; then
    printf '%s\n' 'Build exactly one portable archive and RPM before acceptance testing.' >&2
    exit 1
fi
if rpm -q wubugo >/dev/null 2>&1; then
    printf '%s\n' 'Refusing to alter an existing wubuGO RPM installation.' >&2
    exit 1
fi
task_sandbox="$(mktemp -d "${RUNNER_TEMP:-/tmp}/wubugo-install-test.XXXXXX")"
task_installed_rpm=false
cleanup() {
    if [[ "$task_installed_rpm" == true ]]; then rpm -e wubugo || true; fi
    rm -rf -- "$task_sandbox"
}
trap cleanup EXIT
mkdir -p "$task_sandbox/extracted" "$task_sandbox/user data/wubugo"
printf '%s' 'retained user state' > "$task_sandbox/user data/wubugo/sentinel.txt"
tar -xzf "$task_archive" -C "$task_sandbox/extracted"
task_data="$task_sandbox/user data"
timeout 120s env XDG_DATA_HOME="$task_data" bash "$task_sandbox/extracted/wubuGO/install.sh"
test -x "$task_data/wubugo-app/wubuGO"
test -f "$task_data/applications/wubugo.desktop"
timeout 120s xvfb-run -a "$task_data/wubugo-app/wubuGO" --self-test "$task_root/dist/user-installed-selftest.json"
timeout 120s env XDG_DATA_HOME="$task_data" bash "$task_data/wubugo-app/uninstall.sh"
test ! -e "$task_data/wubugo-app"
test ! -e "$task_data/applications/wubugo.desktop"
test "$(cat "$task_data/wubugo/sentinel.txt")" = 'retained user state'

timeout 120s rpm -Uvh "${task_rpms[0]}"
task_installed_rpm=true
test -x /opt/wubugo/wubuGO
test -f /usr/share/applications/wubugo.desktop
timeout 120s xvfb-run -a /opt/wubugo/wubuGO --self-test "$task_root/dist/rpm-installed-selftest.json"
timeout 120s rpm -e wubugo
task_installed_rpm=false
test ! -e /opt/wubugo/wubuGO
test ! -e /usr/share/applications/wubugo.desktop
test "$(cat "$task_data/wubugo/sentinel.txt")" = 'retained user state'
.build-venv/bin/python - <<'PY'
import json
from pathlib import Path
for name in ('user-installed-selftest.json', 'rpm-installed-selftest.json'):
    result = json.loads((Path('dist') / name).read_text())
    assert result['ok'] is True and result['isolated_state'] is True, result
report = {'ok': True, 'platform': 'Fedora x86_64', 'game_started': False,
          'tests': ['portable archive extraction', 'per-user install', 'path with spaces',
                    'installed GUI self-test', 'per-user uninstall', 'RPM install',
                    'RPM GUI self-test', 'RPM uninstall', 'user state retained']}
Path('dist/installer-smoke.json').write_text(json.dumps(report, indent=2) + '\n')
PY
