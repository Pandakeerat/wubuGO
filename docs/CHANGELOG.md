# 6.0 development release

- Preserved the Python GUI and added pastel-orange branding, a logo, Setup/Downloads/Settings/Integrity pages.
- Bundled pinned 33-firearm historical source; generated MIGI overrides with provenance and explicit engine limits.
- Added queued downloads, checksums, temporary storage, optional Discord presence and explicit staged updates.
- Hardened local launch parameters, protected writes, versioned preferences and rollback.
- Built and tested actual Windows and Fedora runtime/installer packages in native CI.
- In-game HUD/menu and weapon effects remain unverified. Native Linux injection is unsupported.

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
