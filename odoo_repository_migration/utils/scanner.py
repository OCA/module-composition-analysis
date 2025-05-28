# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.addons.odoo_repository.lib.scanner import MigrationScanner


class MigrationScannerOdooEnv(MigrationScanner):
    """MigrationScanner running on the same server than Odoo.

    This class takes an additional `env` parameter (`odoo.api.Environment`)
    used to request Odoo, and implement required methods to use it.
    """

    def __init__(self, *args, **kwargs):
        if kwargs.get("env"):
            self.env = kwargs.pop("env")
        super().__init__(*args, **kwargs)

    def _get_odoo_repository_id(self) -> int:
        return (
            self.env["odoo.repository"]
            .search([("name", "=", self.name), ("org_id", "=", self.org)])
            .id
        )

    def _get_odoo_repository_branches(self, repo_id) -> list[str]:
        args = [
            ("repository_id", "=", repo_id),
            ("branch_id", "in", self.branches),
        ]
        repo_branches = self.env["odoo.repository.branch"].search(args)
        return repo_branches.mapped("branch_id.name")

    def _get_odoo_migration_paths(self, branches: list[str]) -> list[tuple[str]]:
        args = [
            ("source_branch_id", "in", branches),
            ("target_branch_id", "in", branches),
        ]
        migration_paths = self.env["odoo.migration.path"].search(args)
        return [
            (mp.source_branch_id.name, mp.target_branch_id.name)
            for mp in migration_paths
        ]

    def _is_module_blacklisted(self, module):
        return bool(
            self.env["odoo.module"].search_count(
                [("name", "=", module), ("blacklisted", "=", True)]
            )
        )

    def _get_odoo_module_branch_id(self, repo_id: int, module: str, branch: str) -> int:
        args = [
            ("repository_id", "=", repo_id),
            ("module_id", "=", module),
            ("branch_id", "=", branch),
        ]
        return self.env["odoo.module.branch"].search(args).id

    def _get_odoo_module_branch_migration_id(
        self, module_branch_id: int, source_branch: str, target_branch: str
    ) -> int:
        args = [
            ("module_branch_id", "=", module_branch_id),
            ("source_branch_id", "=", source_branch),
            ("target_branch_id", "=", target_branch),
        ]
        migration = self.env["odoo.module.branch.migration"].search(args)
        if migration:
            return migration.id

    def _get_odoo_module_branch_migration_data(
        self, repo_id: int, module: str, source_version: str, target_version: str
    ) -> dict:
        args = [
            ("module_branch_id.repository_id", "=", repo_id),
            ("module_id", "=", module),
            ("source_branch_id", "=", source_version),
            ("target_branch_id", "=", target_version),
        ]
        migration = self.env["odoo.module.branch.migration"].search(args)
        if migration:
            data = {
                "last_source_scanned_commit": migration.module_branch_id.last_scanned_commit,
                "last_target_scanned_commit": (
                    migration.target_module_branch_id.last_scanned_commit
                ),
                "last_source_mig_scanned_commit": migration.last_source_scanned_commit,
                "last_target_mig_scanned_commit": migration.last_target_scanned_commit,
            }
            return data
        return {}

    def _push_scanned_data(self, module_branch_id: int, data: dict):
        res = self.env["odoo.module.branch.migration"].push_scanned_data(
            module_branch_id, data
        )
        # Commit after each scan
        self.env.cr.commit()  # pylint: disable=invalid-commit
        return res
