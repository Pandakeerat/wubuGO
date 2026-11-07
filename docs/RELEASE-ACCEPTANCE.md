# Release acceptance — 6.0 development candidate

This is a development candidate, not a certified cross-platform game restoration.

## Checks performed here

- All local unittest cases (see test-results-v6.txt).
- Syntax compilation of Python modules.
- Real Tk 8.6 graphical navigation of all nine pages.
- Graphical workflow test: bundled source generation; profile installation and rollback; preferences installation; local hash baseline/compare; mocked staged-download rows; harmless native synthetic launch.
- Real HTTPS download of pinned MIGI to a scratch cache; 8,322,321 bytes, expected SHA-256 matched. Payload never run and not redistributed.
- Linux bundled executable GUI startup on Debian 13. This is not execution on Fedora or Windows.

## Required before calling a platform release supported

For each supported Windows/Fedora version, record OS version, architecture, Python/toolchain, Steam package type, game build, MIGI/Bridge commit and test results. Keep game backups outside the installer directory.

1. Build natively using packaging instructions. Verify release archive hashes and runtime/licenses. Install offline on a fresh user account with no Python installed; launch all pages; upgrade; uninstall/reinstall; confirm settings and backups survive and Steam is untouched.
2. Detect and manually select Source 1 across multiple Steam libraries (including Flatpak Steam on Fedora); reject CS2-only folders. Ensure no arbitrary manifest path escapes the library.
3. Test local native/Proton launch against a real game with Steam running. Confirm actual command flags and local map, and inability to override launch parameters from the GUI. Test stopped/running guards and invalid configured paths.
4. Verify a Steam-clean game, record local baseline, deliberately change a disposable file and confirm local comparison. Steam owns depot validation and progress.
5. Install/change/rollback profiles and preferences, including foreign/edited files, corrupt receipt, tampered backup, read-only directory, low disk and interrupted writes. Never overwrite unknown data to make a test pass.
6. On Windows only, separately audit optional upstream Bridge dependencies, licenses and injection procedure in a disposable offline installation. Keep backups of all upstream-modified paths. No automatic external-script execution in this candidate. Capture original Panorama locally, patch/restore ZIP; test every menu action and HUD at multiple resolutions.
7. Build MIGI source overrides, inspect actual built VPK and measure representative damage, armor, magazine, recoil/accuracy/fire timing in a private local game. A matching JSON and generated patch do not prove engine use.
8. Test optional Discord rich presence on both actual Discord clients, with a developer application named exactly wubuGO. Verify game exit restores launcher activity; app exit clears activity.
9. Use a real controlled HTTPS test publisher to check update/asset host rules, failure/cancellation/checksum mismatch, staging and manual platform installer handoff. No arbitrary code auto-execution.

Record failures and mark unsupported integrations explicitly. Do not label the Windows injector as a native Fedora HUD solution. Do not ship the Valve game in the installer.
