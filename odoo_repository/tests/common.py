# Copyright 2024 Camptocamp SA
# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging
import pathlib
import re
import shutil
import tempfile
from unittest.mock import patch

import git
import psutil

from odoo.tests.common import TransactionCase

from .odoo_repo_mixin import OdooRepoMixin

_logger = logging.getLogger(__name__)


class Common(TransactionCase, OdooRepoMixin):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.repositories_path = tempfile.mkdtemp()
        cls.env["ir.config_parameter"].set_param(
            "odoo_repository_storage_path", cls.repositories_path
        )
        # org and repository
        cls.repo_name = cls.repo_upstream_path.parts[-1]
        cls.org = cls.env["odoo.repository.org"].create({"name": cls.fork_org})
        cls.odoo_repository = cls.env["odoo.repository"].create(
            {
                "org_id": cls.org.id,
                "name": cls.repo_name,
                "repo_url": cls.repo_upstream_path,
                "clone_url": cls.repo_upstream_path,
                "repo_type": "github",
            }
        )
        # branch1
        cls.branch1_name = cls.source1.split("/")[1]
        cls.branch = (
            cls.env["odoo.branch"]
            .with_context(active_test=False)
            .search([("name", "=", cls.branch1_name)])
        )
        if not cls.branch:
            cls.branch = cls.env["odoo.branch"].create(
                {
                    "name": cls.branch1_name,
                }
            )
        cls.branch.active = True
        cls._handle_cleanup()
        # branch2
        cls.branch2_name = cls.source2.split("/")[1]
        cls.branch2 = (
            cls.env["odoo.branch"]
            .with_context(active_test=False)
            .search([("name", "=", cls.branch2_name)])
        )
        if not cls.branch2:
            cls.branch2 = cls.env["odoo.branch"].create(
                {
                    "name": cls.branch2_name,
                }
            )
        cls.branch2.active = True
        # branch3
        cls.branch3_name = cls.target2.split("/")[1]
        # technical module
        cls.module_name = cls.addon
        cls.module_branch_model = cls.env["odoo.module.branch"]

    def _patch_github_class(self):
        # Patch helper method part of 'odoo_repository' module
        self.patcher = patch("odoo.addons.odoo_repository.utils.github.request")
        github_request = self.patcher.start()
        github_request.return_value = {}
        self.addCleanup(self.patcher.stop)

    def _update_module_version_on_branch(self, branch, version):
        """Change module version on a given branch, and commit the change."""
        repo = git.Repo(self.repo_upstream_path)
        repo.git.checkout(branch)
        # Update version in manifest file
        lines = []
        with open(self.manifest_path, "r+") as manifest:
            for line in manifest:
                pattern = r".*version['\"]:\s['\"]([\d.]+).*"
                match = re.search(pattern, line)
                if match:
                    current_version = match.group(1)
                    line = line.replace(current_version, version)
                lines.append(line)
        with open(self.manifest_path, "r+") as manifest:
            manifest.writelines(lines)
        # Commit
        repo.index.add(self.manifest_path)
        commit = repo.index.commit(f"[IMP] {self.addon}: bump version to {version}")
        del repo
        return commit.hexsha

    def _update_module_installable_on_branch(self, branch, installable=True):
        repo = git.Repo(self.repo_upstream_path)
        repo.git.checkout(branch)
        # Update installable key in manifest file
        lines = []
        with open(self.manifest_path, "r+") as manifest:
            for line in manifest:
                pattern = r".*installable[`\"]:\s(\b[A-Z,a-z]+),.*"
                match = re.search(pattern, line)
                if match:
                    current_value = match.group(1)
                    line = line.replace(current_value, str(installable))
                lines.append(line)
        with open(self.manifest_path, "r+") as manifest:
            manifest.writelines(lines)
        # Commit
        repo.index.add(self.manifest_path)
        commit = repo.index.commit(
            f"[IMP] {self.addon}: make installable={installable}"
        )
        del repo
        return commit.hexsha

    def _run_odoo_repository_action_scan(self, branch_id, force=False):
        """Run `action_scan` for given `branch_id` on the Odoo repository."""
        self.odoo_repository.with_context(queue_job__no_delay=True).action_scan(
            branch_ids=[branch_id], force=force
        )

    @classmethod
    def _create_odoo_module(cls, name):
        return cls.env["odoo.module"].create({"name": name})

    @classmethod
    def _create_odoo_repository_branch(cls, repo, branch, **values):
        vals = {
            "repository_id": repo.id,
            "branch_id": branch.id,
        }
        vals.update(values)
        return cls.env["odoo.repository.branch"].create(vals)

    @classmethod
    def _create_odoo_module_branch(cls, module, branch, **values):
        vals = {
            "module_id": module.id,
            "branch_id": branch.id,
        }
        vals.update(values)
        return cls.env["odoo.module.branch"].create(vals)

    @classmethod
    def _handle_cleanup(cls):
        """Cleanup dandling git processes once tests are done.

        GitPython is spawning git processes, themselves spawning others
        dettached git processes which can take few seconds to stop afterwards.
        Odoo >= 17.0 is randomly WARNING about such dangling processes when
        running tests (depending if they are already stopped or not),
        so here we are cleaning them before Odoo gets a chance to detect them
        (see 'check_remaining_processes' in 'tests.common.BaseCase').
        """

        def kill_remaining_git_processes():
            current_process = psutil.Process()
            children = current_process.children(recursive=False)
            for child in children:
                if child.name() != "git":
                    continue
                _logger.info("A git process was found, killing it: %s", child)
                child.kill()
            psutil.wait_procs(children, timeout=10)

        cls.addClassCleanup(kill_remaining_git_processes)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(cls.repositories_path)

    def tearDown(self):
        super().tearDown()
        repositories_path = pathlib.Path(self.repositories_path)
        for sub_path in repositories_path.iterdir():
            shutil.rmtree(sub_path)
