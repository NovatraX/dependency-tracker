import os
import json
import yaml
import requests
import datetime
import argparse
from dotenv import load_dotenv
from abc import ABC, abstractmethod
from prettytable import PrettyTable
from typing import List, Dict, Optional

load_dotenv()

# --- Configuration & Constants ---

DEPENDENCIES_FILE = "dependencies.yml"
TRACKING_FILE = "tracked_versions.json"

CURRENT_REPO = os.environ.get("GITHUB_REPOSITORY")

# --- Interfaces / Abstract Base Classes ---


class IGitHubClient(ABC):
    @abstractmethod
    def get_latest_release(self, repo_name: str) -> Optional[Dict]:
        pass

    @abstractmethod
    def check_path_exists(self, repo_name: str, path: str, ref: str) -> bool:
        pass


class IOutputFormatter(ABC):
    @abstractmethod
    def format(self, results: List[Dict]) -> str:
        pass


# --- Implementations ---


class GitHubClient(IGitHubClient):
    def __init__(self, current_repo: Optional[str]):
        self.current_repo = current_repo
        self.headers = {"Accept": "application/vnd.github.v3+json"}

    def get_latest_release(self, repo_name: str) -> Optional[Dict]:
        url = f"https://api.github.com/repos/{repo_name}/releases/latest"
        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            print(f"Release not found for {repo_name} (404).")
        else:
            print(f"Error fetching {repo_name}: {response.status_code}")

        return None

    def check_path_exists(self, repo_name: str, path: str, ref: str) -> bool:
        url = f"https://api.github.com/repos/{repo_name}/contents/{path}?ref={ref}"
        response = requests.get(url, headers=self.headers)
        return response.status_code == 200


class ConfigLoader:
    @staticmethod
    def load_repos(file_path: str) -> List[Dict]:
        if not os.path.exists(file_path):
            print(f"Warning: {file_path} not found.")
            return []

        with open(file_path, "r") as f:
            try:
                data = yaml.safe_load(f)
                repos = data.get("repositories", [])
                # Normalize to list of dicts
                normalized = []
                for item in repos:
                    if isinstance(item, str):
                        normalized.append({"name": item})
                    elif isinstance(item, dict) and "name" in item:
                        normalized.append(item)
                return normalized
            except yaml.YAMLError as e:
                print(f"Error parsing YAML: {e}")
                return []


class AssetDiscoverer:
    def __init__(self, github_client: IGitHubClient):
        self.github_client = github_client

    def discover(self, repo_config: Dict, release_data: Dict) -> List[Dict[str, str]]:
        assets = []

        if "custom_url" in repo_config:
            version = release_data.get("tag_name", "")
            url = repo_config["custom_url"].replace("{version}", version)
            assets.append({"name": "Custom Configuration Link", "url": url})

        release_assets = release_data.get("assets", [])
        real_assets_found = False

        for asset in release_assets:
            assets.append({"name": asset["name"], "url": asset["browser_download_url"]})
            real_assets_found = True

        if not real_assets_found:
            repo_name = repo_config["name"]
            tag_name = release_data.get("tag_name")
            dist_path = repo_config.get("dist_path", "dist")

            if self.github_client.check_path_exists(repo_name, dist_path, tag_name):
                dist_url = f"https://github.com/{repo_name}/tree/{tag_name}/{dist_path}"
                assets.append({"name": f"{dist_path} directory", "url": dist_url})

        return assets


class TableFormatter(IOutputFormatter):
    def format(self, results: List[Dict]) -> str:
        table = PrettyTable()
        table.field_names = ["Package", "Version", "Latest", "Assets"]
        table.align = "l"

        for res in results:
            asset_summary = f"{len(res['Assets'])} found" if res["Assets"] else "None"
            table.add_row(
                [res["Package"], res["Version"], res["Latest"], asset_summary]
            )
        return str(table)


class JsonFormatter(IOutputFormatter):
    def format(self, results: List[Dict]) -> str:
        return json.dumps(results, indent=4)


class MarkdownFormatter(IOutputFormatter):
    def format(self, results: List[Dict]) -> str:
        md_lines = ["# Dependency Release Check", ""]

        # Summary table
        md_lines.extend(
            ["| Package | Current | Latest | Assets |", "|---|---|---|---|"]
        )

        for res in results:
            asset_count = f"{len(res['Assets'])} found" if res["Assets"] else "None"
            status = " 🆕" if res["NewRelease"] else ""
            md_lines.append(
                f"| {res['Package']} | {res['Version']} | {res['Latest']}{status} | {asset_count} |"
            )

        md_lines.append("")

        # Detailed sections
        for res in results:
            md_lines.append(f"## {res['Package']}")

            if res["Assets"]:
                md_lines.append("**Assets:**")
                for asset in res["Assets"]:
                    md_lines.append(f"- [{asset['name']}]({asset['url']})")
                md_lines.append("")

            md_lines.append("**Release Notes:**")
            notes = res.get("ReleaseNotes", "").strip()
            md_lines.append(notes if notes else "None")
            md_lines.append("")

        return "\n".join(md_lines)


class ReleaseTracker:
    def __init__(self, tracking_file: str):
        self.tracking_file = tracking_file
        self.tracked_data = self._load()

    def _load(self) -> Dict:
        if os.path.exists(self.tracking_file):
            try:
                with open(self.tracking_file, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}

    def get_version(self, repo_name: str) -> Optional[str]:
        return self.tracked_data.get(repo_name)

    def update_version(self, repo_name: str, version: str):
        self.tracked_data[repo_name] = version

    def save(self):
        with open(self.tracking_file, "w") as f:
            json.dump(self.tracked_data, f, indent=4)


class ReleaseManager:
    def __init__(
        self,
        github_client: IGitHubClient,
        asset_discoverer: AssetDiscoverer,
        tracker: ReleaseTracker,
    ):
        self.github = github_client
        self.asset_discoverer = asset_discoverer
        self.tracker = tracker

    def check_and_update(self, repos: List[Dict]) -> List[Dict]:
        results = []
        changes_detected = False

        for repo_config in repos:
            repo_name = repo_config["name"]
            release = self.github.get_latest_release(repo_name)

            if not release:
                continue

            tag_name = release.get("tag_name")
            body = release.get("body", "")

            last_version = self.tracker.get_version(repo_name)
            is_new = last_version != tag_name

            assets = self.asset_discoverer.discover(repo_config, release)

            if is_new:
                print(
                    f"New version found for {repo_name}: {tag_name} (was {last_version})"
                )
                self.tracker.update_version(repo_name, tag_name)
                changes_detected = True

            results.append(
                {
                    "Package": repo_name,
                    "Version": last_version if last_version else "None",
                    "Latest": tag_name,
                    "NewRelease": is_new,
                    "Assets": assets,
                    "ReleaseNotes": body,
                }
            )

        if changes_detected:
            self.tracker.save()
            self._update_readme()

        return results

    def _update_readme(self):
        readme_path = "README.md"
        if not os.path.exists(readme_path):
            return

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(readme_path, "r") as f:
                lines = f.readlines()

            new_lines = []
            found = False
            for line in lines:
                if line.startswith("Last check ran on:"):
                    new_lines.append(f"Last check ran on: {now}\n")
                    found = True
                else:
                    new_lines.append(line)

            if not found:
                new_lines.append(f"\nLast check ran on: {now}\n")

            with open(readme_path, "w") as f:
                f.writelines(new_lines)
        except Exception as e:
            print(f"Failed to update README: {e}")


class Application:
    def __init__(self):
        self.github = GitHubClient(CURRENT_REPO)
        self.asset_discoverer = AssetDiscoverer(self.github)
        self.tracker = ReleaseTracker(TRACKING_FILE)
        self.release_manager = ReleaseManager(
            self.github, self.asset_discoverer, self.tracker
        )

    def run(self):
        parser = argparse.ArgumentParser(description="Check for new releases.")
        parser.add_argument(
            "--format",
            choices=["table", "json", "markdown"],
            default="table",
            help="Output format",
        )
        args = parser.parse_args()

        repos = ConfigLoader.load_repos(DEPENDENCIES_FILE)

        results = self.release_manager.check_and_update(repos)

        formatter = self._get_formatter(args.format)
        output_content = formatter.format(results)

        if args.format == "json":
            output_file = "output.json"
        elif args.format == "markdown":
            output_file = "output.md"
        else:
            print(output_content)
            return

        with open(output_file, "w") as f:
            f.write(output_content)
        print(f"Output saved to {output_file}")

    def _get_formatter(self, format_name: str) -> IOutputFormatter:
        if format_name == "json":
            return JsonFormatter()
        elif format_name == "markdown":
            return MarkdownFormatter()
        return TableFormatter()


if __name__ == "__main__":
    app = Application()
    app.run()
