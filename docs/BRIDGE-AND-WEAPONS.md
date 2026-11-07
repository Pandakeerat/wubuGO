# Historical source and Bridge compatibility

## Historical firearm coverage

The bundle now includes all **33 firearms** from the `weapons-1.35.4.4.json` historical snapshot in `twowordbird/csgo-weapon-json-output`, pinned to repository commit `16cf45aa6e77a440a698ac0fc3df4c23f839aa38`. The file itself identifies game version 1.35.4.4; the project's historical target date is 3 August 2016. `data/weapons-1.35.4.4.source.json` records URL, exact SHA-256, retrieval date, and the limitation that this has not been verified in the engine.

`offline_source()` uses this full bundle and verifies its checksum without making network requests. The older 21-weapon subset remains as a compatibility fallback only when the full file is absent. Explicit online refresh fetches the same pinned file and verifies its expected digest. This protects against silently treating a newer game's statistics as 2016 data.

The generated MIGI patch covers all 33 mapped item IDs and all supported numeric source fields. It includes recoil, accuracy, armor ratio, magazine size and fire mode. Unavailable fields remain at the installed client's defaults. Model paths in the historical JSON are references, not redistributed model files. No game binaries, models, textures or complete Valve client are included.

A complete source and successful MIGI generation **do not establish complete 2016 gameplay behavior**. The current engine/server may interpret fields differently, ignore additive overrides, or retain different weapon logic. The build report lists source SHA, missing weapons, missing fields and `in_game_verified: false`. Actual offline tests must measure the changed values on the specific game/MIGI version before claiming compatibility.

## Panorama Bridge audit

Reviewed public upstream `wallbangs/panorama-bridge-csgo` commit `b76af33d3f39aecd774cc21e7088e6bdaa0017e9` on 6 November 2026. `Setup.cmd` and `Launch.cmd` are wrappers around PowerShell scripts. Copying those two CMD files alone does not install the Bridge.

The reviewed implementation needs:

- Compatible Windows x86 Source 1 `csgo.exe`; its injector is not a Fedora-native loader.
- Bridge DLL, injector executable, replacement flag, builder and compatibility patch files.
- MIGI, initialized with its game tree, followed by Build/Update Build.
- The full Scaleform-style Panorama addon and separate resource archive.
- A local original Panorama archive captured from the user's own game and a locally generated replacement archive.
- A standalone Python interpreter for upstream builder scripts. wubuGO's bundled runtime is for wubuGO and is not a general Python command line.

The reviewed launcher passes `-insecure`, but does not enforce `sv_lan 1` or a local map; it can also invoke setup/build scripts. wubuGO therefore keeps arbitrary upstream script execution disabled. Importing files does not execute them or modify the Steam client. Current-menu patching is an integration asset with backup/restore; it is not a verified installed HUD.

`data/bridge_dependencies.json` records hashes and pinned URLs taken from upstream's `install_migi.ps1`, `install_addon.ps1`, and `install_resources.ps1`. They are upstream-tested pins, **not a claim of newest releases**. Optional downloads can be cached and checksum checked, but are never automatically run. These third-party binaries and large game-derived UI/resource archives are not redistributed in wubuGO. Their licensing and runtime suitability require review before redistributing.

`inspect_bridge()` reports script/payload availability, local config problems, game addon folders, cached dependency checksums and platform support. It always reports runtime/in-game verification as false. Linux builds support the launcher and native game workflow; they do not claim a native Bridge/MIGI implementation. Explicit Proton launch of a Windows client also does not prove Windows injector compatibility under Proton.

## Menu patch limits

The patch only accepts a recognizable Source 1 main menu and never overwrites the supplied original archive. Patched output is staged, checked, then published. Existing output is protected. Bridge rollback retains the patched archive and recovers from backup-publication failure.

Play buttons request local Dust II/Mirage with `sv_lan 1`; no matchmaking menu/server-browser button is added. Inventory, watch and settings navigation still depend on the installed client's Panorama API. Their event handlers and actual rendering remain unverified until tested inside the game.
