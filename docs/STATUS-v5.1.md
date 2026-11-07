# v5.1 development update

The Python/Tk GUI and #FFCE9F accent are preserved.

Implemented and tested with synthetic files on Linux:
- Offline Bridge import accepts flat ZIPs and GitHub repository ZIPs including directory entries. Validates extraction limits, Windows paths, duplicate paths and symlinks before publishing. Never executes imported code.
- Manual setup provides a local inventory. Dependency availability is explicitly unverified. No claim that a source ZIP is a complete offline loader bundle.
- External Bridge setup/launch execution disabled until its exact implementation can be reviewed and tested for backups and offline/-insecure enforcement.
- Direct launches include -insecure, sv_lan 1 and a local map. Only a validated map override is accepted; arbitrary exec/connect/launch overrides rejected. Steam URI fallback now uses the same local launcher. This is launch configuration, not a network firewall; do not connect to public servers from the game console.
- Profile rollback restores the prior file, refusing edited profiles. Addon rollback selects the newest numbered backup and retains the replaced version. Both available on Launch page. Rebuild MIGI after restoring addons.
- Addon replacement restores the previous folder if staged publication fails.
- Generated weapon report lists missing weapons and fields and explicitly records in-game verification as false.
- Inno Setup recipe added for per-user install, shortcuts and registered uninstall. It preserves settings and does not touch Steam. Requires Python 3.10+ with Tkinter; no runtime bundled. Recipe has NOT been compiled or tested on Windows. Existing PowerShell installer remains a legacy alternative and is not newly validated.

Verification: 20 unittest cases pass. Python modules compile. Tests use synthetic game folders and mocked process launches; these do not prove engine compatibility.

Outstanding:
- Exact Bridge version and its dependency payloads are not supplied. Inspecting URLs is not dependency verification. No loader/injector bundled or run.
- Existing main-menu patch passes ZIP patch/restore tests only. Its event handlers, HUD, rendering and actual loading remain unverified. No new functional HUD claimed.
- Offline weapon source remains a partial 21-weapon snapshot. Other weapon values are not invented. Full historical source/provenance and engine tests are needed to complete the addon.
- Windows installer compile/install/upgrade/uninstall; Steam detection on real multi-library Windows installs; MIGI builds; in-game offline/private tests and recovery after failures remain unverified.

Windows acceptance sequence: back up game/Bridge first; build installer with ISCC; test install and uninstall in a disposable account; launch GUI; select actual standalone Source 1 install; install/restore a changed profile; install/change/restore addon and rebuild MIGI; launch local map and inspect console flags. Only after separately auditing Bridge scripts/dependencies and backups, test menu/HUD load and rollback in an isolated offline game. Record client/Bridge/MIGI versions, screenshots and measured weapon values before calling any in-game feature verified.
