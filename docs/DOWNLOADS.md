# Downloads and explicit update staging

Construct `DownloadManager(state_root() / 'downloads')` once for the launcher. Construction and history reads perform no network requests. Call `close()` on application shutdown. Downloads run serially on a daemon worker. GUI code must poll `jobs()` on the Tk thread; worker threads never touch Tk.

```python
from modkit.downloads import DownloadManager
manager = DownloadManager(downloads_directory)
job_id = manager.submit('https://your-trusted-host.example/file.zip', 'file.zip',
                        expected_sha256=publisher_sha256, expected_size=publisher_size)
snapshots = manager.jobs()
manager.cancel(job_id)
manager.close()  # cancellation requested without blocking the GUI
```

No real endpoint is configured by this example. URLs must be HTTPS and redirects cannot downgrade to HTTP. Filenames cannot contain paths or Windows reserved names. Existing files, active same-name jobs and case-insensitive collisions are rejected. Data is streamed into `downloads/.partial/<job-id>.part`; size and optional SHA-256 verification precede atomic no-overwrite publication as `downloads/<filename>`. Failed/cancelled partials are removed. This implementation deliberately starts a fresh transfer on retry instead of trusting partial data. Downloads never run scripts, install a dependency or overwrite the running application.

Each independent job snapshot contains:

- `id`, `filename`, `url`, `created_at`, optional `completed_at`
- `status`: `queued`, `downloading`, `verifying`, `complete`, `failed`, `cancelled`, or `interrupted` (restored unfinished history)
- `downloaded`, `total` (bytes or `None`), `progress` (0–1 or `None` when unknown)
- `temporary_path`, `path`, `error`
- `expected_sha256`, computed `sha256`, `sha256_verified`

Display an indeterminate bar when total is unknown. Complete general downloads may have `sha256_verified=False` when no publisher digest was supplied; do not describe them as verified dependencies. History is stored in `downloads/history.json`; interrupted jobs never silently reconnect on startup. Download limit defaults to 2 GiB and request/socket timeout to 30 seconds. Cancellation takes effect between stream reads; a stalled read can take up to its timeout to release.

# App updates

No update URL is invented. The publisher must configure an HTTPS manifest URL and an explicit host allowlist. The same allowlist covers manifest redirects and the asset URLs declared in it. HTTPS and the trusted publisher provide authenticity; a SHA-256 value in that manifest detects damaged or mismatched asset transfers but is not a standalone signature.

```json
{
  "version": "6.1.0",
  "notes": "Release notes",
  "assets": {
    "windows-x64": {
      "url": "https://your-trusted-host.example/wubuGO-6.1.0-setup.exe",
      "filename": "wubuGO-6.1.0-setup.exe",
      "sha256": "replace-with-the-actual-64-character-publisher-digest",
      "size": 123456
    },
    "linux-x64": {
      "url": "https://your-trusted-host.example/wubuGO-6.1.0-linux.tar.gz",
      "filename": "wubuGO-6.1.0-linux.tar.gz",
      "sha256": "replace-with-the-actual-64-character-publisher-digest",
      "size": 123456
    }
  }
}
```

The placeholder digest above is intentionally invalid. Every actual asset must have a valid digest and exact byte size. Manifest size is limited to 128 KiB. Numeric `major.minor.patch` versions are compared as numbers.

```python
from modkit.downloads import check_update, stage_update
release = check_update(configured_manifest_url,
                       current_version='6.0.0', trusted_hosts=configured_hosts)
if release['available']:
    job_id = stage_update(manager, release, 'windows-x64')
```

An update is downloaded and verified only. The user then reviews and runs its installer outside the current process. There is no automatic execution, privileged mutation, unattended replacement or invented public release service.

Verification: `python -m unittest discover -s tests -p test_downloads.py -v` uses mocked HTTP streams to check staging, history, integrity failures, interrupted transfers, limits, cancellation, no-overwrite behavior, HTTPS redirects and update manifest validation. These tests do not establish availability of a production update service.
