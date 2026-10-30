# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

import requests
import yaml

from odoo import Command
from odoo.exceptions import UserError

from odoo.addons.component.core import Component
from odoo.addons.queue_job.exception import RetryableJobError

from ..utils import github

_logger = logging.getLogger(__name__)


class OCARepositorySynchronizer(Component):
    """Component for synchronizing OCA repositories from GitHub configuration.

    This component is syncing the list of OCA repositories in local database
    from https://github.com/OCA/repo-maintainer-conf repository.
    It creates new repositories, updates existing ones, archives those
    no longer declared in the OCA configuration, and renames those renamed
    on GitHub (detected thanks to the permanent redirects GitHub keeps on
    renamed repositories).
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
        - Renaming repositories renamed on GitHub
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
        except github.GitHubRateLimitError as e:
            # Postpone the job until the rate limit is reset, without
            # increasing its retry counter
            raise RetryableJobError(
                "GitHub API rate limit reached, waiting for reset",
                seconds=e.retry_after,
                ignore_retry=True,
            ) from e
        except UserError:
            # e.g. a repository renamed on GitHub collides with an existing
            # record: a manual intervention is required, fail the job
            # immediately with the explicit error message, no blind retries
            raise
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
            dict: Statistics about created/updated/archived/renamed repositories
        """
        stats = {"created": 0, "updated": 0, "archived": 0, "renamed": 0}
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
        # Rename repositories renamed on GitHub, before any other processing,
        # to avoid archiving them and creating a duplicate under their new name
        existing_repos = self._rename_repositories(existing_repos, current_repos, stats)
        # Process current repositories
        for repo_name, repo_data in current_repos.items():
            # Check if repository already exists
            repo = existing_repos.filtered(
                lambda r, repo_name=repo_name: r.name == repo_name
            )
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

    def _rename_repositories(self, existing_repos, current_repos, stats):
        """Rename local records of repositories renamed on GitHub.

        GitHub keeps a permanent redirect on renamed repositories. Each
        repository missing from the OCA configuration is queried on GitHub:
        if the query is redirected, the repository was renamed, and the
        local record is renamed accordingly to preserve its collected
        data, instead of archiving it and creating a duplicate under the
        new name.

        The OCA configuration remains authoritative for the lifecycle of
        a repository: a renamed record is archived by the regular sync
        process until its new name is declared in the configuration, and
        reactivated at that time only (see
        '_prepare_oca_repository_update_vals').

        Args:
            existing_repos: Recordset of existing OCA repositories
            current_repos: Dict of repository data from OCA configuration
            stats: Dict of synchronization statistics to update

        Returns:
            recordset: The existing repositories, without any record
                       deleted to merge duplicates of renamed ones
        """
        env = self.work.env
        renames = []
        for repo in existing_repos:
            if repo.name in current_repos or not repo.active:
                continue
            # The repository is missing from the OCA configuration: ask
            # GitHub about it. A redirected query means the repository
            # was renamed (or transferred), and the returned payload
            # describes the repository under its current name.
            info = github.get_repo_info(env, "OCA", repo.name)
            if not info:
                # Repository deleted from GitHub: keep the archive process
                continue
            new_org, _, new_name = info.get("full_name", "").partition("/")
            if not new_name or new_name == repo.name or new_org != "OCA":
                # Not renamed, or transferred to another organization:
                # keep the archive process
                continue
            renames.append((repo, new_name))
        processed = set()
        for repo, new_name in sorted(renames, key=lambda item: item[0].id):
            # Chain of renames: several old repositories could redirect
            # to the same new name. Only the first one is renamed.
            if new_name in processed:
                _logger.warning(
                    "OCA repository %s was renamed to %s on GitHub, but "
                    "another repository was already renamed to that name: "
                    "archiving %s instead",
                    repo.name,
                    new_name,
                    repo.name,
                )
                continue
            target = (
                env["odoo.repository"]
                .with_context(active_test=False)
                .search([("org_id", "=", repo.org_id.id), ("name", "=", new_name)])
            )
            if target:
                # A record already exists under the new name. GitHub
                # guarantees both records are the same repository.
                # Raise an error, it has to be handled manually to not lose data.
                raise UserError(
                    self.env._(
                        "OCA repository %(old_name)s was renamed to %(new_name)s "
                        "on GitHub, but a record already exists under the new name.",
                        old_name=repo.name,
                        new_name=new_name,
                    )
                )
            repo_url = f"https://github.com/OCA/{new_name}"
            _logger.info(
                "OCA repository %s was renamed to %s on GitHub: renaming "
                "local record (%s)",
                repo.name,
                new_name,
                repo.id,
            )
            repo.write({"name": new_name, "repo_url": repo_url, "clone_url": repo_url})
            processed.add(new_name)
            stats["renamed"] += 1
        return existing_repos.exists()

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
