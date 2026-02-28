# olira-cli — Publishing Guide

This document explains how `olira-cli` is versioned, built, and distributed.

> **PyPI is reserved for the Olira SDK.** The CLI is distributed as a standalone binary
> — no Python installation required for end users.

---

## Distribution Channels

| Channel | Command | Audience |
|---|---|---|
| Homebrew | `brew install raiahealth/tap/olira` | macOS + Linux (primary) |
| Shell script | `curl -fsSL https://install.olira.ai \| sh` | Any Unix (fallback) |
| GitHub Releases | Direct binary download | Manual / CI use |
| AWS CodeArtifact | `pip install olira-cli` | Olira engineers only (private) |

Customers never need Python or pip. Binaries are self-contained executables built with
PyInstaller.

### Why two separate channels?

**CodeArtifact (`olira-cli`)** is a **private** registry — it requires AWS IAM authentication
to access. Only Olira engineers with valid AWS credentials can install from it. It will never
appear on public PyPI, so customers cannot accidentally discover or install it. This mirrors
how `common-models` and `utils` are distributed internally.

**Homebrew / shell script** point to **public GitHub Releases** — no credentials required.
This is the customer-facing distribution path.

**PyPI is intentionally left free** for the future Olira SDK (`pip install olira-sdk` or
similar). Running `pip install olira-cli` from a default PyPI index will return "package not
found".

---

## Package Anatomy

```
packages/
└── olira-cli/
    ├── src/olira_cli/
    │   ├── __init__.py     # __version__ and _INTERNAL_BUILD flag
    │   ├── cli.py          # Argument parser and command dispatch
    │   ├── auth.py         # Login flow and token handling
    │   ├── api.py          # app-api calls (keys, member profile)
    │   └── credentials.py  # Local credential storage and logout
    ├── homebrew/
    │   └── olira.rb        # Homebrew formula template (pushed to raiahealth/homebrew-tap)
    ├── install.sh          # Shell installer (served at https://install.olira.ai)
    ├── pyproject.toml
    ├── uv.lock
    └── CHANGELOG.md
```

---

## The `_INTERNAL_BUILD` Flag

`src/olira_cli/__init__.py` contains:

```python
_INTERNAL_BUILD: bool = True
```

When `True`, internal-only flags are visible in `--help`:

- `--env` (values: `dev`, `stage`, `prod`, `local`)
- `--mcp-server`
- `--console-url`
- `--port`

When `False`, these flags are suppressed via `argparse.SUPPRESS` — they still work but are
not advertised. The flag is **never committed as `False`**; CI patches it before building
customer-facing artifacts.

---

## CI Publish Workflow (`publish-olira-cli.yml`)

Triggered on merge to `main` when `pyproject.toml` or any `.py` file changes.

### Job 1 — `publish-codeartifact`

Reuses `_publish-python-package.yml` — publishes `olira-cli` to all three CodeArtifact
environments in parallel:

| Environment | Repository | `_INTERNAL_BUILD` |
|---|---|---|
| `dev` | `olira-private-dev` | `True` |
| `stage` | `olira-private-stage` | `True` |
| `prod` | `olira-private-prod` | `False` (patched) |

### Job 2 — `release-binaries`

Runs a 3-platform matrix after CodeArtifact succeeds:

| Runner | Binary name |
|---|---|
| `macos-latest` (Apple Silicon) | `olira-macos-arm64` |
| `macos-13` (Intel) | `olira-macos-x86_64` |
| `ubuntu-latest` | `olira-linux-x86_64` |

Each runner:
1. Patches `_INTERNAL_BUILD = False`
2. Runs `pyinstaller --onefile` to produce a single executable
3. Uploads the binary as a workflow artifact

### Job 3 — `create-release`

After all binaries are ready:
1. Downloads all three binaries
2. Computes `sha256sum` checksums
3. Extracts the release notes from `CHANGELOG.md` for the current version
4. Creates (or re-creates) a GitHub Release tagged `olira-cli-v{version}`
5. Attaches all binaries + `checksums.txt`
6. Updates the Homebrew formula in the `raiahealth/homebrew-tap` repo:
   - Bumps `version`
   - Replaces SHA256 placeholders with real checksums
   - Commits and pushes — Homebrew picks it up automatically

---

## Homebrew Tap

> **Status: not yet set up — tracked for a future PR.**

The formula template already exists at `packages/olira-cli/homebrew/olira.rb` and the CI
workflow (`create-release` job) already has the logic to push it. The only missing pieces
are the external GitHub repo and the secret.

### One-time setup (separate PR / task)

#### 1. Create the tap repository

Create a **public** GitHub repository named exactly `homebrew-tap` under the `olira`
org:

```
https://github.com/raiahealth/homebrew-tap
```

Homebrew derives the tap name from the repo name — `raiahealth/homebrew-tap` becomes
`brew tap raiahealth/tap`.

The minimal repo structure required:

```
homebrew-tap/
└── Formula/
    └── olira.rb    ← copy from packages/olira-cli/homebrew/olira.rb for the initial commit
```

#### 2. Create the `HOMEBREW_TAP_TOKEN` secret

Generate a **fine-grained Personal Access Token** (PAT) under a machine/bot account (or the
`olira` org account):

- **Repository access**: `raiahealth/homebrew-tap` only
- **Permissions**: `Contents → Read and Write`

Add it to _this_ repository (`olira-platform`) under:
`Settings → Secrets and variables → Actions → New repository secret`

| Name | Value |
|---|---|
| `HOMEBREW_TAP_TOKEN` | `github_pat_…` |

#### 3. Do a dry-run after the first binary release

After the first `publish-olira-cli.yml` run that includes the `create-release` job, verify
the formula was updated in `raiahealth/homebrew-tap` and test locally:

```bash
brew tap raiahealth/tap
brew install olira
olira --version
```

### How it works end-to-end (once set up)

```
merge to main (version bump)
        │
        ▼
publish-olira-cli.yml
  └─ create-release job
       ├─ creates GitHub Release with binaries
       ├─ computes sha256 checksums
       └─ pushes updated olira.rb to raiahealth/homebrew-tap
                │
                ▼
        brew upgrade olira   ← picks up new version automatically
```

### Customer install commands (once live)

```bash
# One-liner (taps and installs in one step)
brew install raiahealth/tap/olira

# Or explicitly
brew tap raiahealth/tap
brew install olira

# Upgrade
brew upgrade olira
```

---

## Shell Installer (`install.olira.ai`)

> **Status: script is ready — hosting setup tracked for a future PR.**

The script `packages/olira-cli/install.sh` is already written. It auto-detects the OS and
architecture, fetches the latest GitHub Release, and installs the binary to `/usr/local/bin`
(or `~/bin` as a fallback).

### One-time hosting setup (separate PR / task)

#### Option A — CloudFront + S3 (recommended, matches existing infra)

1. Upload `install.sh` to a versioned S3 path:
   `s3://olira-public-prod/cli/install.sh`
2. Create a CloudFront distribution (or reuse an existing one) with:
   - Origin: the S3 bucket
   - Alternate domain: `install.olira.ai`
   - SSL cert via ACM
3. Add a DNS CNAME record: `install.olira.ai → <cloudfront-domain>.cloudfront.net`
4. Add an invalidation step to the CI workflow after each release to bust the cache:
   ```yaml
   - name: Invalidate CloudFront cache
     run: aws cloudfront create-invalidation --distribution-id $CF_DIST_ID --paths "/cli/install.sh"
   ```

#### Option B — Raw GitHub URL (zero infra, immediate)

Point `install.olira.ai` at a redirect to the raw GitHub URL:

```
https://raw.githubusercontent.com/raiahealth/olira-platform/main/packages/olira-cli/install.sh
```

This always serves the `main` branch version with no caching issues. Fine for an early
launch; swap to Option A later for reliability and analytics.

### Customer install command (once live)

```bash
curl -fsSL https://install.olira.ai | sh
```

---

## Release Checklist

When cutting a new release, update all of the following in a single commit:

- [ ] `packages/olira-cli/pyproject.toml` — bump `version`
- [ ] `packages/olira-cli/src/olira_cli/__init__.py` — bump `__version__`
- [ ] `packages/olira-cli/uv.lock` — run `uv lock` or manually update the version line
- [ ] `packages/olira-cli/CHANGELOG.md` — add `## [x.y.z] - YYYY-MM-DD` entry

Verify consistency before pushing:

```bash
bash scripts/check-version.sh
```

CI handles everything else: builds binaries, creates the GitHub Release, updates the
Homebrew formula, and publishes to CodeArtifact.

---

## Required GitHub Secrets

| Secret | Used by | Purpose |
|---|---|---|
| `HOMEBREW_TAP_TOKEN` | `create-release` job | Push formula updates to `raiahealth/homebrew-tap` |

---

## Manual / Emergency Build

If you need to build a binary locally:

```bash
cd packages/olira-cli
uv sync --extra dev

# Patch flag for customer build
sed -i.bak 's/_INTERNAL_BUILD: bool = True/_INTERNAL_BUILD: bool = False/' src/olira_cli/__init__.py

uv run pyinstaller --onefile --name olira --strip src/olira_cli/cli.py
# Binary is at dist/olira

# Restore source
git checkout src/olira_cli/__init__.py
```

---

## Version History

See [CHANGELOG.md](CHANGELOG.md) for the full release history.
