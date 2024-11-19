# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.addons.odoo_repository.tests import common


class TestOdooModuleBranch(common.Common):
    def setUp(self):
        super().setUp()
        self.module = self._create_odoo_module("my_module")
        self.repo_branch = self._create_odoo_repository_branch(
            self.odoo_repository, self.branch
        )
        self.repo_branch2 = self._create_odoo_repository_branch(
            self.odoo_repository, self.branch2
        )
        self.module_branch = self._create_odoo_module_branch(
            self.module,
            self.branch,
            specific=False,
            repository_branch_id=self.repo_branch.id,
            last_scanned_commit="sha",
        )

    def test_migration_scan_removed(self):
        self.module_branch.removed = True
        self.assertFalse(self.module_branch.migration_scan)

    def test_migration_scan_pr_url(self):
        self.module_branch.pr_url = "https://my/pr"
        self.assertFalse(self.module_branch.migration_scan)

    def test_migration_scan_repo_collect_migration_data(self):
        self.assertFalse(self.module_branch.migration_scan)
        self.odoo_repository.collect_migration_data = True
        # It's not enough to flag the module as there is no available
        # migration path to scan
        self.assertFalse(self.module_branch.migration_scan)

    def test_migration_scan_never_scanned(self):
        self.module_branch.last_scanned_commit = False
        self.assertFalse(self.module_branch.migration_scan)
        self.odoo_repository.collect_migration_data = True
        self.assertTrue(self.module_branch.migration_scan)

    def test_migration_scan_missing_migration_path(self):
        self.odoo_repository.collect_migration_data = True
        self.assertFalse(self.module_branch.migration_scan)
        mig_path = self.env["odoo.migration.path"].create(
            {
                "source_branch_id": self.branch.id,
                "target_branch_id": self.branch2.id,
            }
        )
        self.assertTrue(self.module_branch.migration_scan)
        # Once we collected migration data for the expected branch+commit
        # the module doesn't require a migration scan anymore
        self.module_branch.migration_ids |= (
            # Simulate migration data addition
            self.env["odoo.module.branch.migration"].create(
                {
                    "module_branch_id": self.module_branch.id,
                    "migration_path_id": mig_path.id,
                    "last_source_scanned_commit": self.module_branch.last_scanned_commit,
                }
            )
        )
        self.assertFalse(self.module_branch.migration_scan)
