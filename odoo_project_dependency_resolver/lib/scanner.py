# Copyright 2026 ACSONE SA/NV (<https://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging
import pathlib
import tarfile
import tempfile

import git
from odoo_addons_parser import ModuleParser

from odoo.addons.odoo_repository.lib.scanner import BaseScanner

_logger = logging.getLogger(__name__)


class PinnedModuleScanner(BaseScanner):
    """Analyse a module at the revision a project is pinned on.

    A pinned revision is the head of a pull request more often than of a
    branch, so the standard scan of a repository, which walks branches, never
    reaches it. Neither does it reach a module the pull request adds, which
    exists in no branch at all.

    Nothing is cloned: only the revisions a project pins are fetched, without
    the history leading to them nor the branches around them. What a full
    clone would bring is of no use here, a module being read from a single
    commit.
    """

    # The revisions are kept out of the way of the clones the repository
    # scanner maintains: shallow and branchless, they would be of no use to a
    # repository scan, and the repository holding them can be one it scans.
    _revisions_dirname = "pinned-revisions"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.path = self.repositories_path.joinpath(
            self._revisions_dirname, self.org, self.clone_name or self.name
        )

    def scan_module_at_revision(self, module_path, revision):
        """Return the analysis of `module_path` at `revision`, `None` if absent."""
        self._apply_git_global_config()
        self.path.mkdir(parents=True, exist_ok=True)
        repo = git.Repo.init(self.path)
        try:
            self._apply_git_config(repo)
            self._set_git_remote_url(repo, "origin", self.clone_url)
            self._fetch_revision(repo, revision)
            with tempfile.TemporaryDirectory() as tmp_dir:
                module_dir = self._extract_module(repo, revision, module_path, tmp_dir)
                if module_dir is None:
                    return None
                return ModuleParser(module_dir, scan_models=False).to_dict()
        finally:
            repo.close()

    def _fetch_revision(self, repo, revision):
        """Fetch `revision` alone, without the history leading to it.

        Only a revision the repository does not hold yet is fetched: a pinned
        one never moves, so it is worth fetching once and never again. The
        ones fetched before are kept, as the revisions of a repository share
        most of their content.
        """
        if self._has_revision(repo, revision):
            return
        _logger.info("%s: fetch revision %s", self.full_name, revision)
        with self._get_git_env() as env, repo.git.custom_environment(**env):
            repo.git.fetch("origin", revision, depth=1)

    @staticmethod
    def _has_revision(repo, revision):
        """Return whether the local clone already holds `revision`."""
        try:
            repo.commit(revision)
        except (git.exc.BadName, ValueError):
            return False
        return True

    def _extract_module(self, repo, revision, module_path, target_dir):
        """Extract `module_path` at `revision` into `target_dir`.

        Returns the path of the extracted module, `None` when the revision
        holds no such module.

        The module is extracted rather than checked out: the working tree of
        the clone belongs to the scan jobs, which check branches out in it.
        """
        archive = pathlib.Path(target_dir, "module.tar")
        try:
            repo.git.archive(revision, module_path, output=str(archive))
        except git.exc.GitCommandError:
            _logger.warning(
                "%s: no %s at revision %s",
                self.full_name,
                module_path,
                revision,
                exc_info=True,
            )
            return None
        with tarfile.open(archive) as tar:
            tar.extractall(target_dir, filter="data")
        archive.unlink()
        return pathlib.Path(target_dir, module_path)
