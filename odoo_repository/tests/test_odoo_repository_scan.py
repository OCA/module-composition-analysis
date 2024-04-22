# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from .common import Common


class TestOdooRepositoryScan(Common):
    def test_check_config(self):
        self.odoo_repository._check_config()

    def test_action_scan(self):
        module = self.env["odoo.module"].search([("name", "=", self.module_name)])
        self.assertFalse(module)
        self.odoo_repository.with_context(test_queue_job_no_delay=True).action_scan(
            [self.branch.name]
        )
        # Check module technical name
        module = self.env["odoo.module"].search([("name", "=", self.module_name)])
        self.assertTrue(module)
        # Check module branch
        module_branch = self.env["odoo.module.branch"].search(
            [("module_id", "=", module.id), ("branch_id", "=", self.branch.id)]
        )
        self.assertEqual(module_branch.module_name, self.module_name)
        self.assertTrue(module_branch.last_scanned_commit)
        self.assertEqual(module_branch.repository_id, self.odoo_repository)
        self.assertEqual(module_branch.org_id, self.org)
        self.assertEqual(module_branch.title, "Test")
        self.assertEqual(module_branch.category_id.name, "Test Module")
        self.assertItemsEqual(
            module_branch.author_ids.mapped("name"),
            ["Odoo Community Association (OCA)", "Camptocamp"],
        )
        self.assertEqual(module_branch.dependency_ids.module_name, "base")
        self.assertEqual(module_branch.license_id.name, "AGPL-3")
        self.assertEqual(module_branch.version, "1.0.0")
        self.assertEqual(module_branch.version_ids.manifest_value, "1.0.0")
        self.assertEqual(module_branch.version_ids.name, f"{self.branch.name}.1.0.0")
        self.assertEqual(
            module_branch.version_ids.commit, module_branch.last_scanned_commit
        )
        self.assertFalse(module_branch.version_ids.has_migration_script)
        self.assertTrue(module_branch.sloc_python)
        self.assertEqual(module_branch.addons_path, ".")
        # Check repository branch
        repo_branch = module_branch.repository_branch_id
        self.assertEqual(repo_branch.branch_id, self.branch)
        self.assertEqual(
            repo_branch.last_scanned_commit, module_branch.last_scanned_commit
        )
