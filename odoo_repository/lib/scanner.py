# Copyright 2023 Camptocamp SA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)

import contextlib
import json
import logging
import pathlib
import os
import subprocess
import tempfile
import time

import git
import oca_port
from odoo_addons_analyzer import ModuleAnalysis


# Disable logging from 'pygount' (used by odoo_addons_analyzer)
logging.getLogger("pygount").setLevel(logging.ERROR)

_logger = logging.getLogger(__name__)

# TODO handle Git clone/fetch through SSH:
#   https://gitpython.readthedocs.io/en/stable/tutorial.html#handling-remotes
# ssh_cmd = 'ssh -i id_deployment_key'
# with repo.git.custom_environment(GIT_SSH_COMMAND=ssh_cmd):
#         repo.remotes.origin.fetch()


class BaseScanner:
    _dirname = "odoo-repositories"

    def __init__(
        self,
        org: str,
        name: str,
        clone_url: str,
        branches: list,
        repositories_path: str = None,
        ssh_key: str = None,
    ):
        self.org = org
        self.name = name
        self.clone_url = clone_url
        self.branches = branches
        self.repositories_path = self._prepare_repositories_path(
            repositories_path
        )
        self.path = self.repositories_path.joinpath(self.org, self.name)
        self._apply_git_config()
        self.ssh_key = ssh_key

    def scan(self):
        # Clone or update the repository
        if not self.is_cloned:
            self._clone()
        self._fetch()

    @contextlib.contextmanager
    def _get_git_env(self):
        """Context manager yielding env variables used by Git invocations."""
        git_env = {}
        if self.ssh_key:
            with self._get_ssh_key() as ssh_key_path:
                ssh_key_path = "/home/salix/.ssh/testing"   # FIXME test
                git_ssh_cmd = f"ssh -o StrictHostKeyChecking=no -i {ssh_key_path}"
                git_env.update(GIT_SSH_COMMAND=git_ssh_cmd, GIT_TRACE="true")
                yield git_env
        else:
            yield git_env

    @contextlib.contextmanager
    def _get_ssh_key(self):
        """Save the SSH key in a temporary file and yield its path."""
        with tempfile.NamedTemporaryFile() as fp:
            fp.write(self.ssh_key.encode())
            fp.flush()
            ssh_key_path = fp.name
            yield ssh_key_path

    def _prepare_repositories_path(self, repositories_path=None):
        if not repositories_path:
            default_data_dir_path = (
                pathlib.Path.home().joinpath(".local").joinpath("share")
            )
            repositories_path = pathlib.Path(
                os.environ.get("XDG_DATA_HOME", default_data_dir_path),
                self._dirname,
            )
        repositories_path = pathlib.Path(repositories_path)
        repositories_path.mkdir(parents=True, exist_ok=True)
        return repositories_path

    def _apply_git_config(self):
        # This avoids too high memory consumption (default git config could
        # crash the Odoo workers when the scanner is run by Odoo itself).
        subprocess.run(
            ["git", "config", "--global", "core.packedGitLimit", "256m"]
        )
        # self.repo.config_writer().set_value(
        #     "core", "packedGitLimit", "256m").release()

    @property
    def is_cloned(self):
        return self.path.joinpath(".git").exists()

    @property
    def repo(self):
        return git.Repo(self.path)

    @property
    def full_name(self):
        return f"{self.org}/{self.name}"

    def _clone(self):
        _logger.info("Cloning %s...", self.full_name)
        with self._get_git_env() as git_env:
            git.Repo.clone_from(self.clone_url, self.path, env=git_env)

    def _fetch(self):
        repo = self.repo
        _logger.info(
            "%s: fetch branch(es) %s", self.full_name, ", ".join(self.branches)
        )
        for branch in self.branches:
            # Do not block the process if the branch doesn't exist on this repo
            try:
                with self._get_git_env() as git_env:
                    with repo.git.custom_environment(**git_env):
                        repo.remotes.origin.fetch(branch)
            except git.exc.GitCommandError as exc:
                _logger.info(exc)
            else:
                _logger.info("%s: branch %s fetched", self.full_name, branch)

    def _branch_exists(self, branch):
        repo = self.repo
        refs = [r.name for r in repo.remotes.origin.refs]
        branch = f"origin/{branch}"
        return branch in refs

    def _checkout_branch(self, branch):
        self.repo.refs[f"origin/{branch}"].checkout()

    def _get_last_fetched_commit(self, branch):
        """Return the last fetched commit for the given `branch`."""
        repo = self.repo
        return repo.rev_parse(f"origin/{branch}").hexsha

    def _get_module_paths(self, relative_path, branch):
        """Return modules available in `branch`.

        It returns a list of tuples `[(module, last_commit), ...]`.
        """
        # Clean up 'relative_path' to make it compatible with 'git.Tree' object
        relative_tree_path = "/".join(
            [dir_ for dir_ in relative_path.split("/") if dir_ and dir_ != "."]
        )
        # No from_commit means first scan: return all available modules
        branch_commit = self.repo.refs[f"origin/{branch}"].commit
        addons_trees = branch_commit.tree.trees
        if relative_tree_path:
            addons_trees = (branch_commit.tree / relative_tree_path).trees
        return [
            (tree.path, self._get_commit_of_git_tree(f"origin/{branch}", tree))
            for tree in addons_trees
            if self._odoo_module(tree)
        ]

    def _get_module_paths_updated(
            self,
            relative_path,
            from_commit,
            to_commit,
            branch,
            ):
        """Return modules updated between `from_commit` and `to_commit`.

        It returns a list of tuples `[(module, last_commit), ...]`.
        """
        # Clean up 'relative_path' to make it compatible with 'git.Tree' object
        relative_tree_path = "/".join(
            [dir_ for dir_ in relative_path.split("/") if dir_ and dir_ != "."]
        )
        module_paths = set()
        # Same commits: nothing has changed
        if from_commit == to_commit:
            return module_paths
        repo = self.repo
        # Get only modules updated between the two commits
        from_commit = repo.commit(from_commit)
        to_commit = repo.commit(to_commit)
        diffs = to_commit.diff(from_commit, R=True)
        for diff in diffs:
            # Skip diffs that do not belong to the scanned relative path
            if not diff.a_path.startswith(relative_tree_path):
                continue
            # Skip diffs that relates to unrelevant files
            if not self._filter_file_path(diff.a_path):
                continue
            # Exclude files located in root folder
            if "/" not in diff.a_path:
                continue
            # Remove the relative_path (e.g. 'addons/') from the diff path
            rel_path = pathlib.Path(relative_path)
            diff_path = pathlib.Path(diff.a_path)
            module_path = pathlib.Path(
                *diff_path.parts[:len(rel_path.parts) + 1]
            )
            tree = to_commit.tree / str(module_path)
            if self._odoo_module(tree):
                module_paths.add(
                    # FIXME: should we return pathlib.Path objects?
                    (
                        tree.path,
                        self._get_commit_of_git_tree(f"origin/{branch}", tree)
                    )
                )
        return module_paths

    def _filter_file_path(self, path):
        for ext in (".po", ".pot", ".rst", ".html"):
            if path.endswith(ext):
                return False
        return True

    def _get_commit_of_git_tree(self, ref, tree):
        return tree.repo.git.log(
            "--pretty=%H", "-n 1", ref, "--", tree.path
        )

    def _odoo_module(self, tree):
        """Check if the `git.Tree` object is an Odoo module."""
        # NOTE: it seems we could have data only modules without '__init__.py'
        # like 'odoo/addons/test_data_module/', so the Python package check
        # is maybe not useful
        return self._manifest_exists(tree)  # and self._python_package(tree)

    def _python_package(self, tree):
        """Check if the `git.Tree` object is a Python package."""
        return bool(self._get_subtree(tree, "__init__.py"))

    def _manifest_exists(self, tree):
        """Check if the `git.Tree` object contains an Odoo manifest file."""
        manifest_found = False
        for manifest_file in ("__manifest__.py", "__openerp__.py"):
            if self._get_subtree(tree, manifest_file):
                manifest_found = True
                break
        return manifest_found

    def _get_subtree(self, tree, path):
        """Return the subtree `tree / path` if it exists, or `None`."""
        try:
            return tree / path
        except KeyError:
            pass


class MigrationScanner(BaseScanner):

    def __init__(
        self,
        org: str,
        name: str,
        clone_url: str,
        migration_paths: list[tuple[str]],
        repositories_path: str = None,
        ssh_key: str = None,
    ):
        branches = sorted(set(sum([tuple(mp) for mp in migration_paths], ())))
        super().__init__(
            org, name, clone_url, branches, repositories_path, ssh_key
        )
        self.migration_paths = migration_paths

    def scan(self):
        super().scan()
        repo_id = self._get_odoo_repository_id()
        # Get the repository branches from Odoo as the ones we got as parameter
        # could not exist in the repository
        branches = self._get_odoo_repository_branches(repo_id)
        for source_branch, target_branch in self.migration_paths:
            if (
                self._branch_exists(source_branch)
                and self._branch_exists(target_branch)
            ):
                self._scan_migration_path(source_branch, target_branch)

    def _scan_migration_path(self, source_branch, target_branch):
        repo = self.repo
        repo_source_commit = self._get_last_fetched_commit(source_branch)
        repo_target_commit = self._get_last_fetched_commit(target_branch)
        modules = self._get_module_paths(".", source_branch)
        for module, __ in modules:
            module_branch_id = self._get_odoo_module_branch_id(module, source_branch)
            if not module_branch_id:
                _logger.warning(
                    "Module '%s' for branch %s does not exist on Odoo, "
                    "a new scan of the repository is required. Aborted" % (
                        module, source_branch
                    )
                )
                continue
            # For each module and source/target branch:
            #   - get commit of 'module' relative to the last fetched commit
            #   - get commit of 'module' relative to the last scanned commit
            module_source_tree = self._get_subtree(
                repo.commit(repo_source_commit).tree, module
            )
            module_target_tree = self._get_subtree(
                repo.commit(repo_target_commit).tree, module
            )
            module_source_commit = self._get_commit_of_git_tree(
                repo_source_commit, module_source_tree
            )
            module_target_commit = (
                module_target_tree and self._get_commit_of_git_tree(
                    repo_target_commit, module_target_tree
                ) or False
            )
            # Retrieve existing migration data if any and check if it is outdated
            data = self._get_odoo_module_branch_migration_data(
                module, source_branch, target_branch
            )
            if (
                data.get("last_source_scanned_commit") != module_source_commit
                or data.get("last_target_scanned_commit") != module_target_commit
            ):
                self._scan_module(
                    module,
                    module_branch_id,
                    source_branch,
                    target_branch,
                    module_source_commit,
                    module_target_commit,
                )

    def _scan_module(
        self,
        module: str,
        module_branch_id: int,
        source_branch: str,
        target_branch: str,
        source_commit: str,
        target_commit: str
    ):
        """Collect the migration data of a module."""
        # TODO if all the diffs from 'source_commit' to 'target_commit'
        # for the current module relates to unrelevant files (po, rst, html)
        # skip the scan to speed up the process and push only last scanned commits.
        # OCA bots and weblate could update modules in batch to change such files,
        # making the scan of all repositories quite long.
        data = self._run_oca_port(module, source_branch, target_branch)
        data.update(
            {
                "module": module,
                "source_branch": source_branch,
                "target_branch": target_branch,
                "source_commit": source_commit,
                "target_commit": target_commit,
            }
        )
        self._push_scanned_data(module_branch_id, data)
        # Mitigate "GH API rate limit exceeds" error
        time.sleep(4)
        return True

    def _run_oca_port(self, module, source_branch, target_branch):
        _logger.info(
            "%s: collect migration data for '%s' (%s -> %s)",
            self.full_name,
            module,
            source_branch,
            target_branch,
        )
        # Initialize the oca-port app
        params = {
            "from_branch": source_branch,
            "to_branch": target_branch,
            "addon": module,
            "from_org": self.org,
            "from_remote": "origin",
            "repo_path": self.path,
            "repo_name": self.name,
            "output": "json",
            "fetch": False,
        }
        scan = oca_port.App(**params)
        try:
            json_data = scan.run()
        except ValueError as exc:
            _logger.warning(exc)
        else:
            return json.loads(json_data)

    # Hooks method to override by client class

    def _get_odoo_repository_id(self) -> int:
        """Return the ID of the 'odoo.repository' record."""
        raise NotImplementedError

    def _get_odoo_repository_branches(self, repo_id) -> list[str]:
        """Return the relevant branches based on 'odoo.repository.branch'."""
        raise NotImplementedError

    def _get_odoo_migration_paths(self, branches) -> list[tuple[str]]:
        """Return the available migration paths corresponding to `branches`."""
        raise NotImplementedError

    def _get_odoo_module_branch_id(self, module, branch) -> int:
        """Return the ID of the 'odoo.module.branch' record."""
        raise NotImplementedError

    def _get_odoo_module_branch_migration_id(
            self, module, source_branch, target_branch) -> int:
        """Return the ID of 'odoo.module.branch.migration' record."""
        raise NotImplementedError

    def _get_odoo_module_branch_migration_data(
            self, module, source_branch, target_branch) -> dict:
        """Return the 'odoo.module.branch.migration' data."""
        raise NotImplementedError

    def _push_scanned_data(self, module_branch_id, data):
        """Push the scanned module data to Odoo.

        It has to use the 'odoo.module.branch.migration.push_scanned_data'
        RPC endpoint.
        """
        raise NotImplementedError


class RepositoryScanner(BaseScanner):

    def __init__(
        self,
        org: str,
        name: str,
        clone_url: str,
        branches: list,
        addons_paths_data: list,
        repositories_path: str = None,
        ssh_key: str = None,
    ):
        super().__init__(
            org, name, clone_url, branches, repositories_path, ssh_key
        )
        self.addons_paths_data = addons_paths_data

    def scan(self):
        super().scan()
        repo_id = self._get_odoo_repository_id()
        branches_scanned = {}
        for branch in self.branches:
            branches_scanned[branch] = self._scan_branch(repo_id, branch)

    def _scan_branch(self, repo_id, branch):
        if not self._branch_exists(branch):
            return
        branch_id = self._get_odoo_branch_id(repo_id, branch)
        repo_branch_id = self._create_odoo_repository_branch(repo_id, branch_id)
        last_fetched_commit = self._get_last_fetched_commit(branch)
        last_scanned_commit = self._get_repo_last_scanned_commit(repo_branch_id)
        if last_fetched_commit != last_scanned_commit:
            # Checkout the source branch to:
            #   - get the last commit of a module working tree
            #   - perform module code analysis
            self._checkout_branch(branch)
            # Scan relevant subfolders of the repository
            for addons_path_data in self.addons_paths_data:
                self._scan_addons_path(
                    addons_path_data, branch, repo_branch_id,
                    last_fetched_commit, last_scanned_commit
                )
            # Flag this repository/branch as scanned
            self._update_last_scanned_commit(repo_branch_id, last_fetched_commit)
            return True
        return False

    def _scan_addons_path(
        self, addons_path_data, branch, repo_branch_id,
        last_fetched_commit, last_scanned_commit
    ):
        if not last_scanned_commit:
            module_paths = sorted(
                self._get_module_paths(addons_path_data["relative_path"], branch)
            )
        else:
            # Get module paths updated since the last scanned commit
            module_paths = sorted(
                self._get_module_paths_updated(
                    addons_path_data["relative_path"],
                    from_commit=last_scanned_commit,
                    to_commit=last_fetched_commit,
                    branch=branch,
                )
            )
        extra_log = ""
        if addons_path_data["relative_path"] != ".":
            extra_log = f" in {addons_path_data['relative_path']}"
        _logger.info(
            "%s: %s module(s) updated on %s" + extra_log,
            self.full_name,
            len(module_paths),
            branch,
        )
        # Scan each module
        for module_path, last_module_commit in module_paths:
            self._scan_module(
                branch,
                repo_branch_id,
                module_path,
                last_module_commit,
                addons_path_data,
            )

    def _scan_module(
        self,
        branch,
        repo_branch_id,
        module_path,
        last_module_commit,
        addons_path_data,
    ):
        module = module_path.split("/")[-1]
        last_module_scanned_commit = self._get_module_last_scanned_commit(
            repo_branch_id, module
        )
        # Do not scan if the module didn't changed since last scan
        # NOTE we also do this check at the model level so if the process
        # is interrupted (time limit, not enough memory...) we could
        # resume the work where it stopped by skipping already scanned
        # modules.
        if last_module_scanned_commit == last_module_commit:
            return
        _logger.info(
            "%s#%s: scan '%s' ",
            self.full_name,
            branch,
            module_path,
        )
        data = self._run_code_analysis(module_path)
        if data["manifest"]:
            # Insert all flags 'is_standard', 'is_enterprise', etc
            data.update(addons_path_data)
            # Set the last fetched commit as last scanned commit
            data["last_scanned_commit"] = last_module_commit
            self._push_scanned_data(repo_branch_id, module, data)

    def _run_code_analysis(self, module_path):
        """Perform a code analysis of `module_path`."""
        module_analysis = ModuleAnalysis(f"{self.path}/{module_path}")
        return module_analysis.to_dict()

    # Hooks method to override by client class

    def _get_odoo_repository_id(self):
        """Return the ID of the 'odoo.repository' record."""
        raise NotImplementedError

    def _get_odoo_branch_id(self, repo_id, branch):
        """Return the ID of the relevant 'odoo.branch' record.

        If the repository is cloned from a specific branch name
        (like 'master' or 'main'), return the ID of the configured
        Odoo version (`odoo.branch.odoo_version_id`).
        """
        raise NotImplementedError

    def _get_odoo_repository_branch_id(self, repo_id, branch_id):
        """Return the ID of the 'odoo.repository.branch' record."""
        raise NotImplementedError

    def _create_odoo_repository_branch(self, repo_id, branch_id):
        """Create an 'odoo.repository.branch' record and return its ID."""
        raise NotImplementedError

    def _get_repo_last_scanned_commit(self, repo_branch_id):
        """Return the last scanned commit of the repository/branch."""
        raise NotImplementedError

    def _get_module_last_scanned_commit(self, repo_branch_id, module):
        """Return the last scanned commit of the module."""
        raise NotImplementedError

    def _push_scanned_data(self, repo_branch_id, module, data):
        """Push the scanned module data to Odoo.

        It has to use the 'odoo.module.branch.push_scanned_data' RPC endpoint.
        """
        raise NotImplementedError

    def _update_last_scanned_commit(self, repo_branch_id, last_scanned_commit):
        """Update the last scanned commit for the repository/branch."""
        raise NotImplementedError
