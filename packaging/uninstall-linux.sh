#!/usr/bin/env bash
# Removes only a confirmed per-user app install; never touches game/user state.
set -euo pipefail
task_here="$(cd -- "$(dirname -- "$0")" && pwd)"
task_expected="${XDG_DATA_HOME:-$HOME/.local/share}/wubugo-app"
task_expected="$(readlink -m -- "$task_expected")"
if [[ "$task_here" != "$task_expected" || ! -f "$task_here/.wubugo-user-install" ]] ||
   [[ "$(cat -- "$task_here/.wubugo-user-install")" != 'wubugo-user-install-v1' ]]; then
    printf '%s\n' 'This is not a confirmed per-user install; refusing removal.' >&2
    exit 1
fi
task_desktop="${XDG_DATA_HOME:-$HOME/.local/share}/applications/wubugo.desktop"
# A separately modified desktop entry is retained rather than deleting unknown content.
if [[ -f "$task_desktop" ]] && cmp -s -- "$task_desktop" "$task_here/.wubugo-desktop-entry"; then
    rm -- "$task_desktop"
fi
rm -rf -- "$task_here"
printf '%s\n' 'wubuGO application removed. User settings, Steam files and backups were retained.'
