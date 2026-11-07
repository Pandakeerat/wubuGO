# Discord Rich Presence

Rich Presence is optional and off by default. It talks only to the local Discord desktop application using its public IPC protocol. No Discord user token, password, or account login is needed. It adds no Python dependency.

To display **wubuGO** as the application name, create a [Discord Developer application](https://discord.com/developers/applications) named exactly **wubuGO** and enter its numeric Application ID in the launcher settings. Discord controls the displayed application name; an arbitrary ID will show that application's name instead. The launcher does not invent an ID or impersonate another application. A shared official wubuGO application ID can be shipped by a future release maintainer after they create and control that application.

Start Discord desktop before enabling presence. Windows uses local named pipes; Linux checks Unix sockets under XDG_RUNTIME_DIR, /run/user/<uid>, /tmp and common Flatpak and Snap locations. Sandbox permission boundaries can still prevent IPC; the launcher reports connection failure and retries. It never changes Discord's permissions.

Implementation: `Presence(client_id).start(state='In launcher')`, `set_activity(details, state='Offline / private')`, `close()`. Inspect `status` and `error` to show connection state. Presence describes launcher or local game activity, not verified engine modifications. It cannot change the Steam friends-list game name; Steam manages its own game identity.

Validation uses fake IPC transports and protocol frames. Real Discord display on Windows and Fedora remains unverified until tested with a real developer Application ID and desktop client.
