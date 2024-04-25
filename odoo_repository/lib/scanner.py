# Copyright 2023 Camptocamp SA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)

import ast
import contextlib
import json
import logging
import os
import pathlib
import re
import tempfile
import time

import git
import oca_port

from .odoo_addons_analyzer import ModuleAnalysis

# Disable logging from 'pygount' (used by odoo_addons_analyzer)
logging.getLogger("pygount").setLevel(logging.ERROR)

_logger = logging.getLogger(__name__)

# Paths ending with these patterns will be ignored such as if all scanned commits
# update such files, the underlying module won't be scanned to preserve resources.
IGNORE_FILES = [".po", ".pot", "README.rst", "index.html"]

MANIFEST_FILES = ("__manifest__.py", "__openerp__.py")


@contextlib.contextmanager
def set_env(**environ):
    """
    Temporarily set the process environment variables.

    >>> with set_env(PLUGINS_DIR='test/plugins'):
    ...   "PLUGINS_DIR" in os.environ
    True

    >>> "PLUGINS_DIR" in os.environ
    False

    :type environ: dict[str, unicode]
    :param environ: Environment variables to set
    """
    # Copied from:
    # https://stackoverflow.com/questions/2059482/
    # temporarily-modify-the-current-processs-environment
    old_environ = dict(os.environ)
    os.environ.update(environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old_environ)


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
        github_token: str = None,
    ):
        self.org = org
        self.name = name
        self.clone_url = clone_url
        self.branches = branches
        self.repositories_path = self._prepare_repositories_path(repositories_path)
        self.path = self.repositories_path.joinpath(self.org, self.name)
        self.ssh_key = ssh_key
        self.github_token = github_token

    def scan(self, fetch=True):
        # Clone or update the repository
        if not self.is_cloned:
            self._clone()
        self._apply_git_config()
        if fetch:
            self._fetch()

    @contextlib.contextmanager
    def _get_git_env(self):
        """Context manager yielding env variables used by Git invocations."""
        git_env = {}
        if self.ssh_key:
            with self._get_ssh_key() as ssh_key_path:
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
        # This is especially useful to checkout big repositories like odoo/odoo.
        with self.repo.config_writer() as writer:
            writer.set_value("core", "packedGitLimit", "128m")
            writer.set_value("core", "packedGitWindowSize", "32m")
            writer.set_value("pack", "windowMemory", "64m")
            writer.set_value("pack", "threads", "1")

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
            # NOTE: adding 'no_checkout' and 'filter=blob:none' allows fast
            # cloning and reduce memory usage. Blobs will be fetched later on
            # demand, once the git config to reduce memory usage is applied.
            git.Repo.clone_from(
                self.clone_url,
                self.path,
                env=git_env,
                no_checkout=True,
                filter="blob:none",
            )

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
        # Ensure to clean up the repository before a checkout
        self.repo.git.reset("--hard")
        self.repo.git.clean("-xdf")
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
            (tree.path, self._get_last_commit_of_git_tree(f"origin/{branch}", tree))
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
            module_path = pathlib.Path(*diff_path.parts[: len(rel_path.parts) + 1])
            tree = to_commit.tree / str(module_path)
            if self._odoo_module(tree):
                module_paths.add(
                    # FIXME: should we return pathlib.Path objects?
                    (
                        tree.path,
                        self._get_last_commit_of_git_tree(f"origin/{branch}", tree),
                    )
                )
        return module_paths

    def _filter_file_path(self, path):
        for ext in (".po", ".pot", ".rst", ".html"):
            if path.endswith(ext):
                return False
        return True

    def _get_last_commit_of_git_tree(self, ref, tree):
        return tree.repo.git.log("--pretty=%H", "-n 1", ref, "--", tree.path)

    def _get_commits_of_git_tree(self, from_, to_, tree):
        """Returns commits between `from_` and `to_` in chronological order.

        The list of commits can be limited to a `tree`.
        """
        rev_pattern = f"{from_}..{to_}"
        if not from_:
            rev_pattern = to_
        elif not to_:
            rev_pattern = from_
        commits = tree.repo.git.log(
            "--pretty=%H", "-r", rev_pattern, "--reverse", "--", tree.path
        )
        return commits.split()

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
        for manifest_file in MANIFEST_FILES:
            if self._get_subtree(tree, manifest_file):
                manifest_found = True
                break
        return manifest_found

    def _get_subtree(self, tree, path):
        """Return the subtree `tree / path` if it exists, or `None`."""
        try:
            return tree / path
        except KeyError:  # pylint: disable=except-pass
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
        github_token: str = None,
    ):
        branches = sorted(set(sum([tuple(mp) for mp in migration_paths], ())))
        super().__init__(
            org, name, clone_url, branches, repositories_path, ssh_key, github_token
        )
        self.migration_paths = migration_paths

    def scan(self):
        # Clone/fetch has been done during the repository scan, the migration
        # scan will be processed on the current history of commits
        res = super().scan(fetch=False)
        for source_branch, target_branch in self.migration_paths:
            if self._branch_exists(source_branch) and self._branch_exists(
                target_branch
            ):
                self._scan_migration_path(source_branch, target_branch)
        return res

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
                    "a new scan of the repository is required. Aborted"
                    % (module, source_branch)
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
            module_source_commit = self._get_last_commit_of_git_tree(
                repo_source_commit, module_source_tree
            )
            module_target_commit = (
                module_target_tree
                and self._get_last_commit_of_git_tree(
                    repo_target_commit, module_target_tree
                )
                or False
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
                    data.get("last_source_scanned_commit"),
                    data.get("last_target_scanned_commit"),
                )

    def _scan_module(
        self,
        module: str,
        module_branch_id: int,
        source_branch: str,
        target_branch: str,
        source_commit: str,
        target_commit: str,
        source_last_scanned_commit: str,
        target_last_scanned_commit: str,
    ):
        """Collect the migration data of a module."""
        data = {
            "module": module,
            "source_branch": source_branch,
            "target_branch": target_branch,
            "source_commit": source_commit,
            "target_commit": target_commit,
        }
        # If files updated in the module since the last scan are not relevant
        # (e.g. all new commits are updating PO files), we skip the scan but
        # we still push the new source/target commits to Odoo.
        scan_relevant = self._is_scan_module_relevant(
            module,
            source_commit,
            target_commit,
            source_last_scanned_commit,
            target_last_scanned_commit,
        )
        if scan_relevant:
            _logger.info(
                "%s: relevant changes detected in '%s' (%s -> %s)",
                self.full_name,
                module,
                source_branch,
                target_branch,
            )
            oca_port_data = self._run_oca_port(module, source_branch, target_branch)
            data.update(oca_port_data)
        self._push_scanned_data(module_branch_id, data)
        # Mitigate "GH API rate limit exceeds" error
        if scan_relevant:
            time.sleep(4)
        return True

    def _is_scan_module_relevant(
        self,
        module: str,
        source_commit: str,
        target_commit: str,
        source_last_scanned_commit: str,
        target_last_scanned_commit: str,
    ):
        """Determine if scanning the module is relevant.

        As the scan of a module can be quite time consuming, we first check
        the files impacted among all new commits since the last scan.
        If the all files are irrelevants, then we can bypass the scan.
        """
        # The first time we want to scan the module obviously
        if not source_last_scanned_commit:
            return True
        # Module still not available on target branch, no need to re-run a scan
        # as it is still "To migrate" in this case
        if not target_commit:
            return False
        # Module is available on target branch but it wasn't during the last scan
        if not target_last_scanned_commit:
            return True
        # Other cases: check files impacted by new commits both on source & target
        # branches to tell if a scan should be processed
        repo = self.repo
        source_tree = self._get_subtree(repo.commit(source_commit).tree, module)
        target_tree = self._get_subtree(repo.commit(target_commit).tree, module)
        source_new_commits = self._get_commits_of_git_tree(
            source_last_scanned_commit, source_commit, source_tree
        )
        source_to_scan = self._check_relevant_commits(module, source_new_commits)
        target_new_commits = self._get_commits_of_git_tree(
            target_last_scanned_commit, target_commit, target_tree
        )
        target_to_scan = self._check_relevant_commits(module, target_new_commits)
        return source_to_scan or target_to_scan

    def _check_relevant_commits(self, module, commits):
        repo = self.repo
        paths = set()
        for commit_sha in commits:
            commit = repo.commit(commit_sha)
            if commit.parents:
                diffs = commit.diff(commit.parents[0], paths=[module], R=True)
            else:
                diffs = commit.diff(git.NULL_TREE)
            for diff in diffs:
                paths.add(diff.a_path)
                paths.add(diff.b_path)
        for path in paths:
            if all(not path.endswith(pattern) for pattern in IGNORE_FILES):
                return True
        return False

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
            "github_token": self.github_token,
        }
        # Store oca_port cache in the same folder than cloned repositories
        # to boost performance of further calls
        with set_env(XDG_CACHE_HOME=str(self.repositories_path)):
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
        self, module, source_branch, target_branch
    ) -> int:
        """Return the ID of 'odoo.module.branch.migration' record."""
        raise NotImplementedError

    def _get_odoo_module_branch_migration_data(
        self, module, source_branch, target_branch
    ) -> dict:
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
        github_token: str = None,
    ):
        super().__init__(
            org, name, clone_url, branches, repositories_path, ssh_key, github_token
        )
        self.addons_paths_data = addons_paths_data

    def scan(self):
        res = super().scan()
        repo_id = self._get_odoo_repository_id()
        branches_scanned = {}
        for branch in self.branches:
            branches_scanned[branch] = self._scan_branch(repo_id, branch)
        return res

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
                    addons_path_data,
                    branch,
                    repo_branch_id,
                    last_fetched_commit,
                    last_scanned_commit,
                )
            # Flag this repository/branch as scanned
            self._update_last_scanned_commit(repo_branch_id, last_fetched_commit)
            return True
        return False

    def _scan_addons_path(
        self,
        addons_path_data,
        branch,
        repo_branch_id,
        last_fetched_commit,
        last_scanned_commit,
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
        modules_scanned = {}
        for module_path, last_module_commit in module_paths:
            self._scan_module(
                branch,
                repo_branch_id,
                module_path,
                last_module_commit,
                addons_path_data,
            )
            module = module_path.split("/")[-1]
            modules_scanned[module] = True
        return modules_scanned

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
        data = self._run_module_code_analysis(
            module_path, branch, last_module_scanned_commit, last_module_commit
        )
        if data["manifest"]:
            # Insert all flags 'is_standard', 'is_enterprise', etc
            data.update(addons_path_data)
            # Set the last fetched commit as last scanned commit
            data["last_scanned_commit"] = last_module_commit
            self._push_scanned_data(repo_branch_id, module, data)
        return data

    def _run_module_code_analysis(self, module_path, branch, from_commit, to_commit):
        """Perform a code analysis of `module_path`."""
        # Get current code analysis data
        module_analysis = ModuleAnalysis(f"{self.path}/{module_path}")
        data = module_analysis.to_dict()
        # Append the history of versions
        versions = self._read_module_versions(
            module_path, branch, from_commit, to_commit
        )
        data["versions"] = versions
        return data

    def _read_module_versions(self, module_path, branch, from_commit, to_commit):
        """Return versions data introduced between `from_commit` and `to_commit`."""
        versions = {}
        repo = self.repo
        for manifest_file in MANIFEST_FILES:
            manifest_path = "/".join([module_path, manifest_file])
            manifest_tree = self._get_subtree(
                repo.commit(to_commit).tree, manifest_path
            )
            if not manifest_tree:
                continue
            new_commits = self._get_commits_of_git_tree(
                from_commit, to_commit, manifest_tree
            )
            versions_ = self._parse_module_versions_from_commits(
                module_path, manifest_path, branch, new_commits
            )
            versions.update(versions_)
        return versions

    def _parse_module_versions_from_commits(
        self, module_path, manifest_path, branch, new_commits
    ):
        """Parse module versions introduced in `new_commits`."""
        versions = {}
        repo = self.repo
        for commit_sha in new_commits:
            commit = repo.commit(commit_sha)
            if commit.parents:
                diffs = commit.diff(commit.parents[0], R=True)
            else:
                diffs = commit.diff(git.NULL_TREE)
            for diff in diffs:
                # Check only diffs that update the manifest file
                diff_manifest = diff.a_path.endswith(
                    manifest_path
                ) or diff.b_path.endswith(manifest_path)
                if not diff_manifest:
                    continue
                # Try to parse the manifest file
                try:
                    manifest_a = ast.literal_eval(
                        diff.a_blob and diff.a_blob.data_stream.read().decode() or "{}"
                    )
                    manifest_b = ast.literal_eval(
                        diff.b_blob and diff.b_blob.data_stream.read().decode() or "{}"
                    )
                except SyntaxError:
                    _logger.warning(f"Unable to parse {manifest_path} on {branch}")
                    continue
                # Detect version change (added or updated)
                if manifest_a.get("version") == manifest_b.get("version"):
                    continue
                if not manifest_b.get("version"):
                    # Module has been removed? Skipping
                    continue
                version = manifest_b["version"]
                # Skip versions that contains special characters
                # (often human errors fixed afterwards)
                clean_version = re.sub(r"[^0-9\.]", "", version)
                if clean_version != version:
                    continue
                # Detect migration script and bind the version to the commit sha
                migration_path = "/".join([module_path, "migrations", version])
                migration_tree = self._get_subtree(
                    repo.tree(f"origin/{branch}"), migration_path
                )
                values = {
                    "commit": commit_sha,
                    "migration_script": bool(migration_tree),
                }
                versions[version] = values
        return versions

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
