# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

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
        return self.env["odoo.repository"].search(
            [("name", "=", self.name), ("org_id", "=", self.org)]
        ).id

    def _get_odoo_branch_id(self, repo_id, branch):
        repo = self.env["odoo.repository"].browse(repo_id)
        if repo.clone_branch_id and repo.odoo_version_id:
            return repo.odoo_version_id.id
        branch = self.env["odoo.branch"].search(
            [("name", "=", branch), ("odoo_version", "=", True)]
        )
        return branch.id

    def _get_odoo_repository_branch_id(self, repo_id, branch_id):
        args = [
            ("repository_id", "=", repo_id),
            ("branch_id", "=", branch_id),
        ]
        repo_branch = self.env["odoo.repository.branch"].search(args, limit=1)
        if repo_branch:
            return repo_branch.id

    def _create_odoo_repository_branch(self, repo_id, branch_id):
        repo_branch_id = self._get_odoo_repository_branch_id(
            repo_id, branch_id
        )
        if not repo_branch_id:
            values = {
                "repository_id": repo_id,
                "branch_id": branch_id,
            }
            repo_branch_model = self.env["odoo.repository.branch"]
            repo_branch_id = repo_branch_model.create(values).id
        return repo_branch_id

    def _get_repo_last_scanned_commit(self, repo_branch_id):
        repo_branch_model = self.env["odoo.repository.branch"]
        repo_branch = repo_branch_model.browse(repo_branch_id)
        return repo_branch.last_scanned_commit

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
        self.env.cr.commit()
        return res

    def _update_last_scanned_commit(self, repo_branch_id, last_fetched_commit):
        repo_branch_model = self.env["odoo.repository.branch"]
        repo_branch = repo_branch_model.browse(repo_branch_id)
        repo_branch.last_scanned_commit = last_fetched_commit
        # Commit after each repository/branch
        self.env.cr.commit()
        return True
