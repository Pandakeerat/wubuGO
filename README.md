# wubuGO 6.0 — offline-first Source 1 mod launcher

Python/Tk launcher for Windows and Linux, with a pastel-orange `#FFCE9F` interface. It prepares historical weapon overrides and local settings for the standalone Steam Source 1 CS:GO client. It is not CS2 and does not restore the original Scaleform runtime or 2016 engine code.

## Start

A **bundled Windows release** runs `wubuGO.exe`; a **bundled Linux release** runs `./wubuGO`. Both package the manager's Python/Tk runtime. Windows installer and Fedora RPM/portable build instructions are in [packaging/README.md](packaging/README.md). Do not mistake source code or a build recipe for a tested installer.

From source, use Python 3.10+ with Tkinter: `python -m launcher.app`. On Fedora, `START_FEDORA.sh` explains missing system prerequisites. The app uses only the standard library at runtime; no pip downloads at first launch.

1. Open **Setup**. Check bundled asset integrity and select the existing Steam Source 1 installation. If needed, **Install game in Steam** opens Steam's installation workflow. wubuGO never redistributes the game, supplies an account, or bypasses ownership.
2. **Prepare offline assets** builds all 33 sourced firearm overrides. **Prepare game profile** writes the dedicated HUD/preferences profile, preserving differing existing content. MIGI installation/build is a separate Windows-only integration step.
3. Set **Settings** preferences or an existing Proton executable. Preferences use dedicated cfg files with checksummed ownership and versioned backups; they never overwrite `autoexec.cfg`.
4. Use **Launch** for a local map with `-insecure` and `sv_lan 1`. Native Linux is preferred; an explicitly selected installed Proton can run a Windows game. This configures a local session; it is not a firewall. Do not connect modified clients to public servers.
5. Use **Integrity** for official Steam validation or a distinct, user-recorded local hash baseline. Steam displays its own repair progress.

## Included

- Existing Python GUI, new icon and nine pages: Overview, Setup, Weapons, Classic UI, Launch, Downloads, Settings, Integrity and Diagnostics.
- Complete 33-firearm historical source snapshot pinned to an upstream commit and SHA-256. MIGI addon generation, full provenance and field coverage report. Engine behavior remains unverified.
- Explicit HTTPS download queue with byte progress, cancellation, history, checksums, temporary files and staged outputs. Bundled files need no downloads. No automatic network request at startup.
- Optional pinned Bridge dependency downloads, offline ZIP import and detailed local inventory. Imported or downloaded scripts are never automatically run.
- Config backups, addon replacement recovery, rollback, running-game guards and linked-path protection.
- Optional Discord rich presence using local IPC, no tokens or extra packages. To display **wubuGO**, create a Discord application with exactly that name and enter its public Application ID in Settings. Disabled by default.
- Explicit update check/staging from the wubuGO repository release manifest, with optional trusted publisher overrides. Nothing is checked at startup; checksums validate transfer, not publisher identity. No automatic code execution or replacement of a running app.

## Downloads and app data

Installed resources are read-only. All mutable data lives at:

- Windows: `%LOCALAPPDATA%\wubuGO`
- Linux/Fedora: `${XDG_DATA_HOME:-~/.local/share}/wubugo`
- Optional override for portable/testing use: `WUBUGO_DATA_DIR`

Open **Downloads** to see the actual path. `Downloads/.partial/<job>.part` holds temporary transfers; only a complete validated transfer is published to `Downloads/<filename>`. Unknown totals show an animated bar and actual byte count, not a fabricated percentage. Install/build operations show activity bars; file hashing shows measured file progress. Steam's own downloads remain in Steam.

Uninstalling the manager leaves user settings, downloads, game changes and recovery files in place. Restore game changes before uninstalling if you want to undo them. Rebuild MIGI after addon rollback.

## Honest compatibility status

| Component | Status |
| --- | --- |
| Offline assets, generation, backups, recovery, downloader, settings, detection command construction | Automated local tests pass |
| Linux source GUI, all nine pages, synthetic end-to-end workflows | Graphically tested with real Tk 8.6 |
| Bundled Linux runtime | Built and GUI-started on Debian 13; **not Fedora-tested** |
| Windows executable / Inno installer | Build pipeline provided; **not compiled or executed on Windows here** |
| Fedora RPM / portable build pipeline | Provided; requires native Fedora build and execution testing |
| Actual game, Steam library discovery on real PCs, Proton game runtime | **Unverified** |
| MIGI/Bridge HUD, menu event handlers and firearm effects | **Unverified in-game** |
| Native Linux MIGI/Bridge injection | **Unsupported**; upstream uses a Windows x86 injector |
| Real Discord display | IPC mock-tested; needs Discord + a real Application ID |

See [Bridge and weapon audit](docs/BRIDGE-AND-WEAPONS.md), [downloads/update API](docs/DOWNLOADS.md), [rich presence](docs/PRESENCE.md), and [release acceptance](docs/RELEASE-ACCEPTANCE.md).

## Verification

`python -m unittest discover -s tests -v`

For explicit GUI workflow testing on a real display: `python tests/smoke_gui.py`. It uses temporary app data, synthetic game files, a mocked download, and a harmless native test executable. It does not start the real game.

No Valve client binaries, paid content, Steam credentials or injector payloads are bundled. Historical JSON includes file-path references, not those game assets. Third-party optional dependency pins are compatibility references, not a claim that every latest upstream revision is safe or compatible. Older v5 documentation is retained under docs for history and is superseded by this README.
