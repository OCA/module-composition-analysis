# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

import requests
import yaml

from odoo import Command

from odoo.addons.component.core import Component
from odoo.addons.queue_job.exception import RetryableJobError

from ..utils import github

_logger = logging.getLogger(__name__)


class OCARepositorySynchronizer(Component):
    """Component for synchronizing OCA repositories from GitHub configuration.

    This component is syncing the list of OCA repositories in local database
    from https://github.com/OCA/repo-maintainer-conf repository.
    It creates new repositories, updates existing ones, and archive those
    no longer declared in the OCA configuration.
    """

    _name = "oca.repository.synchronizer"
    _collection = "odoo.mca.backend"
    _usage = "oca.repository.synchronizer"

    github_conf_api_url = "repos/OCA/repo-maintainer-conf/contents/conf/repo"

    def _get_oca_repo_blacklist(self):
        """Get OCA repository blacklist from configuration parameter.

        Returns:
            list: List of repository names to skip during synchronization
        """
        param_value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("odoo_repository.oca_repo_blacklist", default="")
        )
        return [repo.strip() for repo in param_value.split(",") if repo.strip()]

    def run(self):
        """Execute OCA repository synchronization.

        Fetches repository configurations from OCA/repo-maintainer-conf,
        parses the YAML files, and synchronizes the local repository database by:
        - Creating new repositories that exist in OCA config but not locally
        - Updating existing repositories with any changes
        - Archiving repositories that no longer exist in OCA config
        """
        try:
            # Fetch YAML configurations from GitHub
            repo_configs = self._fetch_oca_repo_configurations()
            # Parse and extract repository data
            current_repos = self._parse_oca_repo_configurations(repo_configs)
            # Sync repositories (create/update/archive)
            stats = self._sync_oca_repositories(current_repos)
            _logger.info("OCA repository sync completed: %s", stats)
            return stats
        except Exception as e:
            raise RetryableJobError("Failed to fetch OCA repositories") from e

    def _fetch_oca_repo_configurations(self):
        """Fetch OCA repository configurations from GitHub.

        Returns:
            dict: Repository configurations keyed by filename
        """
        try:
            # Get list of files in conf/repo directory
            files = github.request(self.work.env, self.github_conf_api_url)
            repo_configs = {}
            for file_info in files:
                if file_info["name"].endswith(".yml"):
                    # Fetch the actual YAML content
                    download_url = file_info["download_url"]
                    response = requests.get(download_url, timeout=30)
                    response.raise_for_status()
                    repo_configs[file_info["name"]] = response.text
            return repo_configs
        except Exception as e:
            _logger.error("Failed to fetch OCA repo configurations: %s", str(e))
            raise

    def _parse_oca_repo_configurations(self, repo_configs: dict):
        """Parse YAML configurations and extract OCA repository data.

        Args:
            repo_configs: Dict of filename -> YAML content

        Returns:
            dict: Repository data keyed by repository name, only including
                  repositories with non-empty branches
        """
        current_repos = {}
        for filename, yaml_content in repo_configs.items():
            try:
                # Parse YAML content
                data = yaml.safe_load(yaml_content)
                if not data:
                    continue
                # Process each repository in the YAML file
                for repo_name, repo_config in data.items():
                    # Get blacklist from backend configuration
                    blacklist = self._get_oca_repo_blacklist()
                    if repo_name in blacklist:
                        _logger.info("Skipping import of OCA repository %s", repo_name)
                        continue
                    # Skip repositories with default_branch = 'master' or 'main'
                    # These are not hosting Odoo modules
                    default_branch = repo_config.get("default_branch", "")
                    if default_branch in ["master", "main"]:
                        _logger.info(
                            "Skipping OCA repository %s "
                            "(default_branch=%s, not hosting Odoo modules)",
                            repo_name,
                            default_branch,
                        )
                        continue
                    # Only include repositories with branches.
                    # Others repositories are probably not hosting Odoo modules.
                    branches = repo_config.get("branches", [])
                    if not branches:
                        continue
                    # Construct repository URLs
                    repo_url = f"https://github.com/OCA/{repo_name}"  # noqa: E231
                    current_repos[repo_name] = {
                        "name": repo_name,
                        "repo_url": repo_url,
                        "clone_url": repo_url,
                        "repo_type": "github",
                    }
            except yaml.YAMLError as e:
                _logger.warning("Failed to parse YAML file %s: %s", filename, str(e))
                continue
            except Exception as e:
                _logger.warning("Error processing file %s: %s", filename, str(e))
                continue
        return current_repos

    def _sync_oca_repositories(self, current_repos):
        """Synchronize OCA repositories with current configuration.

        Args:
            current_repos: Dict of repository data from OCA configuration

        Returns:
            dict: Statistics about created/updated/archived repositories
        """
        stats = {"created": 0, "updated": 0, "archived": 0}
        env = self.work.env
        # Get OCA organization
        oca_org = env.ref(
            "odoo_repository.odoo_repository_org_oca", raise_if_not_found=False
        )
        if not oca_org:
            _logger.warning("OCA organization not found in database")
            return stats
        # Get existing OCA repositories
        odoo_repository = env["odoo.repository"]
        existing_repos = odoo_repository.with_context(active_test=False).search(
            [("org_id", "=", oca_org.id)]
        )
        # Process current repositories
        for repo_name, repo_data in current_repos.items():
            # Check if repository already exists
            repo = existing_repos.filtered(lambda r: r.name == repo_name)
            if repo:
                # Update existing repository
                update_vals = self._prepare_oca_repository_update_vals(repo_data)
                # Only update if values have changed
                if any(repo[field] != update_vals[field] for field in update_vals):
                    repo.write(update_vals)
                    stats["updated"] += 1
            else:
                # Create new repository
                create_vals = self._prepare_oca_repository_create_vals(repo_data)
                odoo_repository.create(create_vals)
                stats["created"] += 1
        # Archive repositories that no longer exist in configuration
        for repo in existing_repos:
            if repo.name not in current_repos and repo.active:
                repo.active = repo.to_scan = False
                stats["archived"] += 1
        return stats

    def _prepare_oca_repository_update_vals(self, repo_data):
        return {
            "repo_url": repo_data["repo_url"],
            "clone_url": repo_data["clone_url"],
            "repo_type": repo_data["repo_type"],
            "active": True,
        }

    def _prepare_oca_repository_create_vals(self, repo_data):
        oca_org = self.work.env.ref("odoo_repository.odoo_repository_org_oca")
        addons_path_community = self.work.env.ref(
            "odoo_repository.odoo_repository_addons_path_community"
        )
        return {
            "org_id": oca_org.id,
            "name": repo_data["name"],
            "repo_url": repo_data["repo_url"],
            "clone_url": repo_data["clone_url"],
            "repo_type": repo_data["repo_type"],
            "active": True,
            "sequence": 200,
            "to_scan": True,  # Enable scanning by default
            "addons_path_ids": [Command.link(addons_path_community.id)],
        }
