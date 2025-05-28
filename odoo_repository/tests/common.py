# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import os
import pathlib
import re
import tempfile
from unittest.mock import patch

import git
from oca_port.tests.common import CommonCase

from odoo.tests.common import TransactionCase


class Common(TransactionCase, CommonCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        CommonCase.setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.repositories_path = tempfile.mkdtemp()
        cls.env["ir.config_parameter"].set_param(
            "odoo_repository_storage_path", cls.repositories_path
        )
        cls._apply_git_config()

    def setUp(self):
        super().setUp()
        # Leverage the existing test class from 'oca_port' to bootstrap
        # temporary git repositories to run tests
        CommonCase.setUp(self)
        self.repo_name = pathlib.Path(self.repo_upstream_path).parts[-1]
        self.org = self.env["odoo.repository.org"].create({"name": self.fork_org})
        self.odoo_repository = self.env["odoo.repository"].create(
            {
                "org_id": self.org.id,
                "name": self.repo_name,
                "repo_url": self.repo_upstream_path,
                "clone_url": self.repo_upstream_path,
                "repo_type": "github",
            }
        )
        # branch1
        self.branch1_name = self.source1.split("/")[1]
        self.branch = (
            self.env["odoo.branch"]
            .with_context(active_test=False)
            .search([("name", "=", self.branch1_name)])
        )
        if not self.branch:
            self.branch = self.env["odoo.branch"].create(
                {
                    "name": self.branch1_name,
                }
            )
        self.branch.active = True
        # branch2
        self.branch2_name = self.source2.split("/")[1]
        self.branch2 = (
            self.env["odoo.branch"]
            .with_context(active_test=False)
            .search([("name", "=", self.branch2_name)])
        )
        if not self.branch2:
            self.branch2 = self.env["odoo.branch"].create(
                {
                    "name": self.branch2_name,
                }
            )
        self.branch2.active = True
        # branch3
        self.branch3_name = self.target2.split("/")[1]
        # technical module
        self.module_name = self.addon
        self.module_branch_model = self.env["odoo.module.branch"]

    @classmethod
    def _apply_git_config(cls):
        """Configure git (~/.gitconfig) if no config file exists."""
        git_cfg = pathlib.Path(os.path.expanduser("~/.gitconfig"))
        if git_cfg.exists():
            return
        os.system("git config --global user.email 'test@example.com'")
        os.system("git config --global user.name 'test'")

    def _patch_github_class(self):
        res = super()._patch_github_class()
        # Patch helper method part of 'odoo_repository' module as well
        self.patcher2 = patch("odoo.addons.odoo_repository.utils.github.request")
        github_request = self.patcher2.start()
        github_request.return_value = {}
        self.addCleanup(self.patcher2.stop)
        return res

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
        return commit.hexsha

    def _run_odoo_repository_action_scan(self, branch_id, force=False):
        """Run `action_scan` for given `branch_id` on the Odoo repository."""
        self.odoo_repository.with_context(queue_job__no_delay=True).action_scan(
            branch_ids=[branch_id], force=force
        )

    def _create_odoo_module(self, name):
        return self.env["odoo.module"].create({"name": name})

    def _create_odoo_repository_branch(self, repo, branch, **values):
        vals = {
            "repository_id": repo.id,
            "branch_id": branch.id,
        }
        vals.update(values)
        return self.env["odoo.repository.branch"].create(vals)

    def _create_odoo_module_branch(self, module, branch, **values):
        vals = {
            "module_id": module.id,
            "branch_id": branch.id,
        }
        vals.update(values)
        return self.env["odoo.module.branch"].create(vals)
