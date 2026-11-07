# Bundled Windows and Fedora builds

The release installer/portable bundle includes Python, Tcl/Tk, application code,
logo, templates, historical stat source and generated addons. The installed app
needs no Python installer or pip connection. Steam, the game, MIGI and external
Bridge binaries are separate dependencies and are never secretly downloaded or
included as though they were verified. The manager can prepare an offline profile
without those optional tools. Game setup remains explicit and reversible.

## Windows x64

On a Windows build machine install Python 3.13 x64 with Tcl/Tk, Visual Studio C++ Build Tools (x64), Inno Setup 6 and
run `powershell -ExecutionPolicy Bypass -File packaging\build.ps1` from the project
root. This installs pinned build-only PyInstaller into `.build-venv`, runs tests,
freezes the app and compiles an Inno installer. Build internet is required for the
build dependency; users of the resulting artifacts need no Python/downloads.

Outputs: `dist/wubuGO-6.0.1-windows-x64-setup.exe`, portable ZIP and SHA256SUMS.
The installer runs without admin rights, registers uninstall and creates shortcuts.
It installs only the manager into `%LOCALAPPDATA%\Programs\wubuGO`. User settings
and backups live in `%LOCALAPPDATA%\wubuGO` and survive app uninstall/upgrade.
Unsigned builds may produce Windows reputation prompts; no signing claim is made.
Inno Setup must be on PATH or in `Program Files (x86)\Inno Setup 6`.

## Fedora x86_64

On Fedora install build dependencies using
`sudo dnf install python3-devel python3-pip python3-tkinter binutils rpm-build gcc xorg-x11-server-Xvfb xorg-x11-xauth`.
Then run `bash packaging/build-linux.sh`. The output is a frozen portable tar.gz
and RPM. The runtime bundle includes Python/Tcl/Tk; glibc and normal desktop X11
libraries remain system requirements. Build on the oldest supported Fedora target;
a binary built on a newer glibc is not automatically compatible with older distros.
The supplied workflow targets Fedora 43. Fedora Linux support must be validated on
that target; building on this Debian cloud host cannot establish Fedora compatibility.

Extract the portable archive and run `./wubuGO/wubuGO`, or run its `install.sh` for
an offline per-user application-menu install. That helper uses Bash and core utilities, with no system Python requirement. It refuses to overwrite an existing installation. To upgrade,
close the app and move the old `~/.local/share/wubugo-app` directory aside before
running the new helper. User data remains in `~/.local/share/wubugo`. Run the installed `uninstall.sh` to remove only the confirmed per-user app installation and its unchanged shortcut.
The RPM installs application files in `/opt/wubugo`; install it using Fedora's
normal `dnf install ./wubugo-*.rpm` workflow. RPM uninstall retains user state.

## CI and validation

`.github/workflows/build-release.yml` builds native Windows and Fedora artifacts
on a pull request, manual dispatch or a version tag, runs tests and uploads build artifacts. Each build must pass the frozen application’s offline `--self-test` on a real/virtual display before packaging; Windows uses its desktop session and Fedora uses Xvfb. The self-test renders every GUI page, validates bundled assets and builds the 33-weapon addon, writing `frozen-selftest.json`. It does not test the actual game or install anything on the user's PC. Ordinary pull-request runs only build and test.
Native Windows and Fedora 43 CI has passed for the first release candidate, including actual installer self-tests. See the root README and docs/release-6.0 for evidence. Game integration remains unverified.

Before distribution, test fresh installation, no-network launch, paths with spaces,
upgrade with retained settings, uninstall with retained backups, GUI icons and all
Steam/private-game workflows on clean Windows and Fedora test machines. Check the
SHA256SUMS file and scan/sign native artifacts as appropriate. Windows and Fedora
native builds cannot be cross-compiled reliably with PyInstaller from the current
Linux environment; use the native CI jobs. No compiled Windows executable is
claimed unless it is actually present in the output.

## Runtime notices

The build runs `collect_licenses.py` against the frozen directory before archiving.
It copies known Python, Tcl/Tk and PyInstaller/bootloader license texts, and Linux
package copyright/license files for bundled native libraries into
`THIRD-PARTY-LICENSES/`. Its JSON manifest records sources, versions, SHA-256
hashes and unresolved entries. Windows Python's `LICENSE.txt` includes its
third-party runtime notices; individual DLL coverage still requires review. This
is a notice collector, not a legal compliance claim. Review missing entries and
the applicable redistribution terms before publishing artifacts.

## Publish a verified prerelease

Create the matching draft release first. From Actions, manually run **Build and test installers** on `main`, set `publish_release` to true, and supply its draft tag (initially `v6.0.1-rc.1`). Both native build/installation jobs must pass. The separate publisher job verifies their checksums/reports, uploads the runtime packages plus source/evidence archives, publishes the prerelease, then updates `releases/update-manifest.json` with the actual file hashes. Normal pull-request builds cannot publish.

Only the publisher has `contents: write`; it uses GitHub's scoped Actions token and requires no personal token or repository secret. It rejects a changed main branch or an already published release. The generated feed update is a normal fast-forward commit, never a force push. If a later feed push fails, the previous feed remains in place; the published packages stay downloadable and the failed run requires maintainer attention.

The Windows build compiles a small native loader regression fixture outside the release bundle. Every frozen and installed self-test must show that a raw child selects an intentionally wrong DLL, the sanitized child selects its own correct DLL, and the manager's search directory is restored. The fixture is not shipped as a game dependency and never loads game files. Linux self-tests verify restoration of the external child's library path.
