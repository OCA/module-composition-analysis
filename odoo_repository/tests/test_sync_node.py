# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from .common import Common


class TestSyncNode(Common):
    def test_sync_node(self):
        # Scan a repository
        self.odoo_repository.with_context(queue_job__no_delay=True).action_scan(
            self.branch.ids
        )
        # Check data to sync
        data = self.env["odoo.module.branch"]._get_modules_data()
        self.assertEqual(len(data), 1)  # 1 module scanned
        module = data[0]
        self.assertEqual(module["module"], self.module_name)
        self.assertEqual(module["branch"], self.branch.name)
        self.assertEqual(module["version"], "1.0.0")
        self.assertTrue(module["versions"])
        self.assertEqual(module["addons_path"], ".")
        self.assertEqual(module["repository"]["name"], self.odoo_repository.name)
        self.assertEqual(module["repository"]["org"], self.odoo_repository.org_id.name)
        self.assertEqual(
            module["repository"]["repo_type"], self.odoo_repository.repo_type
        )
        self.assertEqual(
            module["repository"]["repo_url"], self.odoo_repository.repo_url
        )
        # Sync these data with a node
        # NOTE as we are using the same node to sync with in tests, we change
        # the content of the data to sync to create a new module
        data[0].update(
            module="synced",
            version="2.0.0",
            branch=self.branch2_name,
        )
        new_module = self.env["odoo.module"].search([("name", "=", "synced")])
        self.assertFalse(new_module)
        self.env["odoo.repository"]._import_data(data)
        nb_modules = self.env["odoo.module"].search_count([])
        self.assertTrue(nb_modules >= 2)
        new_module = self.env["odoo.module.branch"].search(
            [("module_name", "=", "synced")]
        )
        self.assertTrue(new_module)
        self.assertEqual(new_module.version, "2.0.0")
        self.assertEqual(new_module.branch_id.name, self.branch2_name)
        # Existing module didn't changed
        existing_module = self.env["odoo.module.branch"].search(
            [("module_name", "=", self.module_name)]
        )
        self.assertTrue(existing_module)
        self.assertEqual(existing_module.version, "1.0.0")
        self.assertEqual(existing_module.branch_id, self.branch)
