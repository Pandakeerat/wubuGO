#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ -x ./wubuGO ]; then exec ./wubuGO; fi
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'Source launch needs Python and Tk. On Fedora run: sudo dnf install python3 python3-tkinter' >&2
    exit 1
fi
if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
    printf '%s\n' 'Python Tk is missing. On Fedora run: sudo dnf install python3-tkinter' >&2
    exit 1
fi
exec python3 -m launcher.app
