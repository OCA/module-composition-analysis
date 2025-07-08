# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.tools import config

from ..lib.scanner import RepositoryScanner


class RepositoryScannerOdooEnv(RepositoryScanner):
    """RepositoryScanner running on the same server than Odoo.

    This class takes an additional `env` parameter (`odoo.api.Environment`)
    used to request Odoo, and implement required methods to use it.
    """

    def __init__(self, *args, **kwargs):
        if kwargs.get("env"):
            self.env = kwargs.pop("env")
        super().__init__(*args, **kwargs)

    def _get_odoo_repository_id(self):
        return (
            self.env["odoo.repository"]
            .search([("name", "=", self.name), ("org_id", "=", self.org)])
            .id
        )

    def _get_odoo_branch_id(self, version):
        return self.env["odoo.branch"].search([("name", "=", version)]).id

    def _get_odoo_repository_branch_id(self, repo_id, branch_id):
        args = [
            ("repository_id", "=", repo_id),
            ("branch_id", "=", branch_id),
        ]
        repo_branch = self.env["odoo.repository.branch"].search(args, limit=1)
        if repo_branch:
            return repo_branch.id

    def _create_odoo_repository_branch(self, repo_id, branch_id, cloned_branch=None):
        repo_branch_id = self._get_odoo_repository_branch_id(repo_id, branch_id)
        if not repo_branch_id:
            values = {
                "repository_id": repo_id,
                "branch_id": branch_id,
            }
            if cloned_branch:
                values["cloned_branch"] = cloned_branch
            repo_branch_model = self.env["odoo.repository.branch"]
            repo_branch_id = repo_branch_model.create(values).id
        return repo_branch_id

    def _get_repo_last_scanned_commit(self, repo_branch_id):
        repo_branch_model = self.env["odoo.repository.branch"]
        repo_branch = repo_branch_model.browse(repo_branch_id)
        return repo_branch.last_scanned_commit

    def _is_module_blacklisted(self, module):
        return bool(
            self.env["odoo.module"].search_count(
                [("name", "=", module), ("blacklisted", "=", True)]
            )
        )

    def _get_module_last_scanned_commit(self, repo_branch_id, module_name):
        module_branch_model = self.env["odoo.module.branch"]
        args = [
            ("repository_branch_id", "=", repo_branch_id),
            ("module_name", "=", module_name),
        ]
        module = module_branch_model.search(args)
        return module.last_scanned_commit

    def _push_scanned_data(self, repo_branch_id, module, data):
        res = self.env["odoo.module.branch"].push_scanned_data(
            repo_branch_id, module, data
        )
        # Commit after each module
        if not config["test_enable"]:
            self.env.cr.commit()  # pylint: disable=invalid-commit
        return res

    def _update_last_scanned_commit(self, repo_branch_id, last_fetched_commit):
        repo_branch_model = self.env["odoo.repository.branch"]
        repo_branch = repo_branch_model.browse(repo_branch_id)
        repo_branch.last_scanned_commit = last_fetched_commit
        # Commit after each repository/branch
        if not config["test_enable"]:
            self.env.cr.commit()  # pylint: disable=invalid-commit
        return True
