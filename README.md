# Dependency Tracker

Monitors GitHub repositories for new releases and tracks version updates automatically.

## Features

- Tracks multiple GitHub repositories for new releases
- Discovers release assets (binaries, archives, distribution directories)
- Supports custom download URLs
- Multiple output formats (table, JSON, markdown)
- Automatic README timestamp updates
- Persistent version tracking

## Setup

### Prerequisites

- Python 3.7+
- GitHub Personal Access Token (optional, increases API rate limits)

### Installation

```bash
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file:

```bash
GITHUB_REPOSITORY=owner/repo
```

- `GITHUB_REPOSITORY`: Your repository in format `owner/repo`

## Configuration

### dependencies.yml

Define repositories to track:

```yaml
repositories:
  - name: owner/repo-name
  - name: owner/another-repo
    custom_url: https://example.com/download/{version}
    dist_path: build
```

**Fields:**

- `name` (required): GitHub repository in `owner/repo` format
- `custom_url` (optional): Custom download URL with `{version}` placeholder
- `dist_path` (optional): Directory path to check for assets (default: `dist`)

### tracked_versions.json

Automatically maintained file storing last known versions. Do not edit manually.

## Usage

### Basic Usage

```bash
python scripts/check_releases.py
```

### Output Formats

```bash
# Table format (default) - prints to console
python scripts/check_releases.py --format table

# JSON format - saves to output.json
python scripts/check_releases.py --format json

# Markdown format - saves to output.md
python scripts/check_releases.py --format markdown
```

### Output Examples

**Table Format:**

```bash
+------------------+---------+--------+----------+
| Package          | Version | Latest | Assets   |
+------------------+---------+--------+----------+
| owner/repo       | v1.0.0  | v1.1.0 | 3 found  |
+------------------+---------+--------+----------+
```

**Markdown Format:**

Includes a summary table at the top showing all packages with their current/latest versions and asset counts, followed by detailed sections for each package containing:

- Downloadable assets with links
- Full release notes

**JSON Format:**

Structured JSON output with all release information including package names, versions, assets, and release notes.

## How It Works

1. Reads repository list from `dependencies.yml`
2. Fetches latest release from GitHub API for each repository
3. Compares with tracked versions in `tracked_versions.json`
4. Discovers release assets (official assets, custom URLs, or dist directories)
5. Updates tracked versions if new releases found
6. Updates README timestamp when changes detected
7. Outputs results in specified format

### Asset Discovery

The tool discovers assets in three ways:

1. **Official GitHub release assets** - binaries, archives attached to releases
2. **Custom URLs** - if `custom_url` is configured in dependencies.yml
3. **Distribution directories** - checks for `dist_path` directory in the release tag

## Architecture

### Core Components

- **GitHubClient**: GitHub API interactions (releases, file checks)
- **ConfigLoader**: Loads repository configuration from YAML
- **AssetDiscoverer**: Finds downloadable assets for releases
- **ReleaseTracker**: Manages version tracking state
- **ReleaseManager**: Orchestrates check and update process
- **Formatters**: Output results (Table, JSON, Markdown)

### Design Patterns

- Interface-based design with abstract base classes (IGitHubClient, IOutputFormatter)
- Dependency injection for testability
- Single Responsibility Principle

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Check Dependencies
on:
  schedule:
    - cron: '0 0 * * *'  # Daily at midnight
  workflow_dispatch:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.x'
      - run: pip install -r requirements.txt
      - run: python scripts/check_releases.py --format markdown
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
      - name: Commit changes
        run: |
          git config user.name github-actions
          git config user.email github-actions@github.com
          git add tracked_versions.json README.md output.md
          git commit -m "Update tracked versions" || exit 0
          git push
```

## Troubleshooting

### Rate Limiting

- Without token: 60 requests/hour
- With token: 5000 requests/hour
- Solution: Add `GITHUB_TOKEN` to `.env`

### 404 Errors

Repository may not have any releases. Verify the repository has published releases on GitHub.

### No Assets Found

If no assets are found:

- Check if the release has attached assets
- Configure `custom_url` for custom download links
- Configure `dist_path` if assets are in a specific directory

## Last Update Check

Last check ran on: 2026-01-29 01:47:10
