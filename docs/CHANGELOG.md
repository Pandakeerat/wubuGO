# v4 improvements over previous prototype

- Replaced the flat Tk launcher with a polished 5-page studio and real status indicators.
- Removed fabricated server entries and their fake status claims.
- Used the actual pinned **28 July 2016** file rather than asking for another user upload.
- Added one-click historical schema download, validation, report generation, automatic HUD configuration and conditional MIGI installation.
- Fixed prefab inheritance (classic weapon attributes are frequently in `weapon_*_prefab`).
- Removed the required `--current` modern schema argument when building a genuine historic override; current CS:GO can package this elsewhere.
- Improved repeat installs with backup rotation and atomic staging of MIGI addons.
- Integrated opt-in Panorama Bridge download, installer (Steam folder pre-filled), game launch and menu patch/revert.
- All modded launch paths use `-insecure`. Vanilla Steam client also launches insecure in this local mod workbench.
- No unverified matchmaking/service lists; no Valve binaries distributed.
- Tests cover source validation, weapon overlay, game launch construction, repeat installs, bridge ZIP safety and rollback.
