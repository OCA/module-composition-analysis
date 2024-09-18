# Copyright 2023 Camptocamp SA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)

import ast
import contextlib
import json
import logging
import os
import pathlib
import re
import shutil
import tempfile
import time
from urllib.parse import urlparse, urlunparse

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
        repo_type: str = None,
        ssh_key: str = None,
        token: str = None,
        workaround_fs_errors: bool = False,
    ):
        self.org = org
        self.name = name
        self.clone_url = self._prepare_clone_url(repo_type, clone_url, token)
        self.branches = branches
        self.repositories_path = self._prepare_repositories_path(repositories_path)
        self.path = self.repositories_path.joinpath(self.org, self.name)
        self.repo_type = repo_type
        self.ssh_key = ssh_key
        self.token = token
        self.workaround_fs_errors = workaround_fs_errors

    def scan(self, fetch=True):
        res = True
        self._apply_git_global_config()
        # Clone or update the repository
        if not self.is_cloned:
            res = self._clone()
        with self.repo() as repo:
            self._apply_git_config(repo)
            self._set_git_remote_url(repo)
            if fetch:
                res = self._fetch(repo)
        return res

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

    @staticmethod
    def _prepare_clone_url(repo_type, clone_url, token):
        """Return the URL used to clone/fetch the repository.

        If a token is provided it will be inserted automatically.
        """
        if repo_type in ("github", "gitlab") and token:
            parts = list(urlparse(clone_url))
            if parts[0].startswith("http"):
                # Update 'netloc' part to prefix it with the OAuth token
                parts[1] = f"oauth2:{token}@" + parts[1]
                clone_url = urlunparse(parts)
        return clone_url

    @classmethod
    def _prepare_repositories_path(cls, repositories_path=None):
        if not repositories_path:
            default_data_dir_path = (
                pathlib.Path.home().joinpath(".local").joinpath("share")
            )
            repositories_path = pathlib.Path(
                os.environ.get("XDG_DATA_HOME", default_data_dir_path),
                cls._dirname,
            )
        repositories_path = pathlib.Path(repositories_path)
        repositories_path.mkdir(parents=True, exist_ok=True)
        return repositories_path

    def _apply_git_global_config(self):
        # Avoid 'fatal: detected dubious ownership in repository' errors
        # when performing operations in git repositories in case they are
        # cloned on an mounted filesystem with specific options.
        # NOTE: ensure to unset existing entry before adding one, as git doesn't
        # check if an entry already exists, generating duplicates
        os.system('git config --global --unset safe.directory "%s"' % (self.path))
        os.system('git config --global --add safe.directory "%s"' % (self.path))

    def _apply_git_config(self, repo):
        with repo.config_writer() as writer:
            # This avoids too high memory consumption (default git config could
            # crash the Odoo workers when the scanner is run by Odoo itself).
            # This is especially useful to checkout big repositories like odoo/odoo.
            writer.set_value("core", "packedGitLimit", "128m")
            writer.set_value("core", "packedGitWindowSize", "32m")
            writer.set_value("pack", "windowMemory", "64m")
            writer.set_value("pack", "threads", "1")
            # Avoid issues with file permissions for mounted filesystems
            # with specific options.
            writer.set_value("core", "filemode", "false")
            # Disable some GC features for performance (memory and IO)
            # Reflog clean up is triggered automatically by some commands.
            # We assume that we scan upstream branches that will never contain
            # orphaned commits to clean up, so some GC features are useless in
            # this context.
            writer.set_value("gc", "pruneExpire", "never")
            writer.set_value("gc", "worktreePruneExpire", "never")
            writer.set_value("gc", "reflogExpire", "never")
            writer.set_value("gc", "reflogExpireUnreachable", "never")

    def _set_git_remote_url(self, repo):
        """Ensure that 'origin' remote is set with the right URL."""
        # Check first the URL before setting it, as this triggers a 'chmod'
        # command on '.git/config' file (to protect sensitive data) that could
        # be not allowed on some mounted file systems.
        if repo.remotes["origin"].url != self.clone_url:
            repo.remotes["origin"].set_url(self.clone_url)

    @property
    def is_cloned(self):
        return self.path.joinpath(".git").exists()

    @contextlib.contextmanager
    def repo(self):
        repo = git.Repo(self.path)
        try:
            yield repo
        finally:
            del repo

    @property
    def full_name(self):
        return f"{self.org}/{self.name}"

    def _clone_params(self, **extra):
        params = {
            "url": self.clone_url,
            "to_path": self.path,
            # NOTE: adding 'no_checkout' and 'filter=blob:none' allows fast
            # cloning and reduce memory usage. Blobs will be fetched later on
            # demand, once the git config to reduce memory usage is applied.
            "no_checkout": True,
            "filter": "blob:none",
            # Avoid issues with file permissions
            # "allow_unsafe_options": True,
            # "multi_options": ["--config core.filemode=false"],
        }
        params.update(extra)
        return params

    def _clone(self):
        _logger.info("Cloning %s...", self.full_name)
        tmp_git_dir_path = None
        repo_git_dir_path = pathlib.Path(self.path, ".git")
        with tempfile.TemporaryDirectory() as tmp_git_dir:
            if self.workaround_fs_errors:
                tmp_git_dir_path = pathlib.Path(tmp_git_dir).joinpath(".git")
            with self._get_git_env() as git_env:
                extra = {"env": git_env}
                if self.workaround_fs_errors:
                    extra["separate_git_dir"] = str(tmp_git_dir_path)
                params = self._clone_params(**extra)
                git.Repo.clone_from(**params)
                if tmp_git_dir_path:
                    # {repo_path}/.git folder is a hardlink, replace
                    # it by the .git folder created in /tmp
                    # NOTE: use shutil instead of 'pathlib.Path.replace()' as
                    # file systems could be different
                    repo_git_dir_path.unlink()
                    shutil.move(tmp_git_dir_path, repo_git_dir_path)
        return True

    def _fetch(self, repo):
        _logger.info(
            "%s: fetch branch(es) %s", self.full_name, ", ".join(self.branches)
        )
        branches_fetched = []
        for branch in self.branches:
            # Do not block the process if the branch doesn't exist on this repo
            try:
                with self._get_git_env() as git_env:
                    with repo.git.custom_environment(**git_env):
                        repo.remotes.origin.fetch(branch)
            except git.exc.GitCommandError as exc:
                _logger.error(exc)
                if "couldn't find remote ref" in str(exc):
                    _logger.info(
                        "Couldn't find remote branch %s, skipping.", self.full_name
                    )
                    return False
                raise
            else:
                _logger.info("%s: branch %s fetched", self.full_name, branch)
                branches_fetched.append(branch)
        # Return True as soon as we fetched at least one branch
        return bool(branches_fetched)

    def _branch_exists(self, repo, branch):
        refs = [r.name for r in repo.remotes.origin.refs]
        branch = f"origin/{branch}"
        return branch in refs

    def _checkout_branch(self, repo, branch):
        # Ensure to clean up the repository before a checkout
        repo.git.reset("--hard")
        repo.git.clean("-xdf")
        repo.remotes.origin.refs[f"{branch}"].checkout()

    def _get_last_fetched_commit(self, repo, branch):
        """Return the last fetched commit for the given `branch`."""
        return repo.rev_parse(f"remotes/origin/{branch}").hexsha

    def _get_module_paths(self, repo, relative_path, branch):
        """Return modules available in `branch`.

        It returns a list of tuples `[(module, last_commit), ...]`.
        """
        # Clean up 'relative_path' to make it compatible with 'git.Tree' object
        relative_tree_path = "/".join(
            [dir_ for dir_ in relative_path.split("/") if dir_ and dir_ != "."]
        )
        # No from_commit means first scan: return all available modules
        branch_commit = repo.refs[f"origin/{branch}"].commit
        addons_trees = branch_commit.tree.trees
        if relative_tree_path:
            addons_trees = (branch_commit.tree / relative_tree_path).trees
        module_paths = [
            (tree.path, self._get_last_commit_of_git_tree(f"origin/{branch}", tree))
            for tree in addons_trees
            if self._odoo_module(tree)
        ]
        return module_paths

    def _get_module_paths_updated(
        self,
        repo,
        relative_path,
        from_commit,
        to_commit,
        branch,
    ):
        """Return modules updated between `from_commit` and `to_commit`.

        It returns a list of tuples `[(module, last_commit), ...]`.
        If a module has been removed, the tuple returned will be `(module, None)`.
        """
        # Clean up 'relative_path' to make it compatible with 'git.Tree' object
        relative_tree_path = "/".join(
            [dir_ for dir_ in relative_path.split("/") if dir_ and dir_ != "."]
        )
        module_paths = set()
        # Same commits: nothing has changed
        if from_commit == to_commit:
            return module_paths
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
            tree = self._get_subtree(to_commit.tree, str(module_path))
            if tree:
                # Module still exists
                if self._odoo_module(tree):
                    module_paths.add(
                        # FIXME: should we return pathlib.Path objects?
                        (
                            tree.path,
                            self._get_last_commit_of_git_tree(f"origin/{branch}", tree),
                        )
                    )
            else:
                # Module removed
                tree = self._get_subtree(from_commit.tree, str(module_path))
                if self._odoo_module(tree):
                    module_paths.add((tree.path, None))
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
        repo_type: str = None,
        ssh_key: str = None,
        token: str = None,
        workaround_fs_errors: bool = False,
    ):
        branches = sorted(set(sum([tuple(mp) for mp in migration_paths], ())))
        super().__init__(
            org,
            name,
            clone_url,
            branches,
            repositories_path,
            repo_type,
            ssh_key,
            token,
            workaround_fs_errors,
        )
        self.migration_paths = migration_paths

    def scan(self):
        # Clone/fetch has been done during the repository scan, the migration
        # scan will be processed on the current history of commits
        res = super().scan(fetch=False)
        # 'super()' could return False if the branch to scan doesn't exist,
        # there is nothing to scan then.
        if not res:
            return False
        for source_branch, target_branch in self.migration_paths:
            with self.repo() as repo:
                if self._branch_exists(repo, source_branch) and self._branch_exists(
                    repo, target_branch
                ):
                    self._scan_migration_path(repo, source_branch, target_branch)
        return res

    def _scan_migration_path(self, repo, source_branch, target_branch):
        repo_source_commit = self._get_last_fetched_commit(repo, source_branch)
        repo_target_commit = self._get_last_fetched_commit(repo, target_branch)
        modules = self._get_module_paths(repo, ".", source_branch)
        for module, __ in modules:
            if self._is_module_blacklisted(module):
                _logger.info(
                    "%s: '%s' is blacklisted (no migration scan)",
                    self.full_name,
                    module,
                )
                continue
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
                    repo,
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
        repo: git.Repo,
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
            repo,
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
        repo: git.Repo,
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
        source_tree = self._get_subtree(repo.commit(source_commit).tree, module)
        target_tree = self._get_subtree(repo.commit(target_commit).tree, module)
        source_new_commits = self._get_commits_of_git_tree(
            source_last_scanned_commit, source_commit, source_tree
        )
        source_to_scan = self._check_relevant_commits(repo, module, source_new_commits)
        target_new_commits = self._get_commits_of_git_tree(
            target_last_scanned_commit, target_commit, target_tree
        )
        target_to_scan = self._check_relevant_commits(repo, module, target_new_commits)
        return source_to_scan or target_to_scan

    def _check_relevant_commits(self, repo, module, commits):
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
            "github_token": self.repo_type == "github" and self.token or None,
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
        repo_type: str = None,
        ssh_key: str = None,
        token: str = None,
        workaround_fs_errors: bool = False,
    ):
        super().__init__(
            org,
            name,
            clone_url,
            branches,
            repositories_path,
            repo_type,
            ssh_key,
            token,
            workaround_fs_errors,
        )
        self.addons_paths_data = addons_paths_data

    def scan(self):
        res = super().scan()
        # 'super()' could return False if the branch to scan doesn't exist,
        # there is nothing to scan then.
        if not res:
            return False
        repo_id = self._get_odoo_repository_id()
        branches_scanned = {}
        with self.repo() as repo:
            for branch in self.branches:
                branches_scanned[branch] = self._scan_branch(repo, repo_id, branch)
        return res

    def _scan_branch(self, repo, repo_id, branch):
        if not self._branch_exists(repo, branch):
            return
        branch_id = self._get_odoo_branch_id(repo_id, branch)
        repo_branch_id = self._create_odoo_repository_branch(repo_id, branch_id)
        last_fetched_commit = self._get_last_fetched_commit(repo, branch)
        last_scanned_commit = self._get_repo_last_scanned_commit(repo_branch_id)
        if last_fetched_commit != last_scanned_commit:
            # Checkout the source branch to:
            #   - get the last commit of a module working tree
            #   - perform module code analysis
            self._checkout_branch(repo, branch)
            # Scan relevant subfolders of the repository
            for addons_path_data in self.addons_paths_data:
                self._scan_addons_path(
                    repo,
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
        repo,
        addons_path_data,
        branch,
        repo_branch_id,
        last_fetched_commit,
        last_scanned_commit,
    ):
        if not last_scanned_commit:
            module_paths = sorted(
                self._get_module_paths(repo, addons_path_data["relative_path"], branch)
            )
        else:
            # Get module paths updated since the last scanned commit
            module_paths = sorted(
                self._get_module_paths_updated(
                    repo,
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
                repo,
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
        repo,
        branch,
        repo_branch_id,
        module_path,
        last_module_commit,
        addons_path_data,
    ):
        module = module_path.split("/")[-1]
        if self._is_module_blacklisted(module):
            _logger.info(
                "%s#%s: '%s' is blacklisted (no scan)",
                self.full_name,
                branch,
                module_path,
            )
            return
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
        data = {}
        if last_module_commit:
            _logger.info(
                "%s#%s: scan '%s' ",
                self.full_name,
                branch,
                module_path,
            )
            data = self._run_module_code_analysis(
                repo,
                module_path,
                branch,
                last_module_scanned_commit,
                last_module_commit,
            )
        else:
            _logger.info(
                "%s#%s: '%s' removed",
                self.full_name,
                branch,
                module_path,
            )
        # Insert all flags 'is_standard', 'is_enterprise', etc
        data.update(addons_path_data)
        # Set the last fetched commit as last scanned commit
        data["last_scanned_commit"] = last_module_commit
        self._push_scanned_data(repo_branch_id, module, data)
        return data

    def _run_module_code_analysis(
        self, repo, module_path, branch, from_commit, to_commit
    ):
        """Perform a code analysis of `module_path`."""
        # Get current code analysis data
        module_analysis = ModuleAnalysis(f"{self.path}/{module_path}")
        data = module_analysis.to_dict()
        # Append the history of versions
        versions = self._read_module_versions(
            repo, module_path, branch, from_commit, to_commit
        )
        data["versions"] = versions
        return data

    def _read_module_versions(self, repo, module_path, branch, from_commit, to_commit):
        """Return versions data introduced between `from_commit` and `to_commit`."""
        versions = {}
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
                repo, module_path, manifest_path, branch, new_commits
            )
            versions.update(versions_)
        return versions

    def _parse_module_versions_from_commits(
        self, repo, module_path, manifest_path, branch, new_commits
    ):
        """Parse module versions introduced in `new_commits`."""
        versions = {}
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

    def _is_module_blacklisted(self, module):
        """Check if `module` is blacklisted (and should not be scanned)."""
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
