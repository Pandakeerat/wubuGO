#!/usr/bin/env bash
# Offline, per-user install of the frozen portable Linux bundle. No sudo.
set -euo pipefail
task_source="$(cd -- "$(dirname -- "$0")" && pwd)"
task_dest="${XDG_DATA_HOME:-$HOME/.local/share}/wubugo-app"
task_apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
if [[ "$task_source" == "$task_dest" ]]; then
    printf '%s\n' 'Already installed here.'
    exit 0
fi
if [[ ! -x "$task_source/wubuGO" || ! -d "$task_source/_internal" ]]; then
    printf '%s\n' 'Extract the entire portable bundle before installing.' >&2
    exit 1
fi
# Desktop Exec fields need a second level of escaping beyond shell quoting.
# Reject control characters in user-selected XDG paths rather than write a bad entry.
if [[ "$task_dest" == *$'\n'* || "$task_dest" == *$'\r'* ]]; then
    printf '%s\n' 'Newlines in install paths are unsupported.' >&2
    exit 1
fi
if [[ -e "$task_dest" ]]; then
    printf '%s\n' 'An installation already exists. Rename/remove wubugo-app before installing this version; user data is separate.' >&2
    exit 1
fi
mkdir -p -- "$(dirname -- "$task_dest")" "$task_apps"
task_stage="$(mktemp -d "$(dirname -- "$task_dest")/.wubugo-install.XXXXXX")"
trap 'rm -rf -- "$task_stage"' EXIT
cp -a -- "$task_source/." "$task_stage/"
# Desktop Exec fields need escaping independent of shell quoting.
task_exec="$task_dest/wubuGO"
task_exec="${task_exec//\\/\\\\}"
task_exec="${task_exec//\"/\\\"}"
task_exec="${task_exec//\`/\\\`}"
task_exec="${task_exec//\$/\\\$}"
task_exec="${task_exec//%/%%}"
printf '[Desktop Entry]\nType=Application\nName=wubuGO\nExec="%s"\nIcon=%s\nTerminal=false\nCategories=Game;Utility;\n' \
    "$task_exec" "$task_dest/wubugo.png" > "$task_stage/.wubugo-desktop-entry"
if [[ -e "$task_apps/wubugo.desktop" ]]; then
    printf '%s\n' 'An existing wubuGO desktop entry was found; move it aside before installation.' >&2
    exit 1
fi
printf '%s\n' 'wubugo-user-install-v1' > "$task_stage/.wubugo-user-install"
# Prepare everything before publishing the application directory.
mv -- "$task_stage" "$task_dest"
if ! cp -- "$task_dest/.wubugo-desktop-entry" "$task_apps/wubugo.desktop"; then
    rm -rf -- "$task_dest"
    exit 1
fi
printf 'Installed to %s\nStart wubuGO from your application menu. User data and game backups remain separate.\n' "$task_dest"
