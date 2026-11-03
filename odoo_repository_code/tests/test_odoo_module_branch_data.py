# Copyright 2026 Sébastien Alix <https://github.com/sebalix>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import shutil

import git

from odoo.addons.odoo_repository.tests.common import Common
from odoo.addons.odoo_repository.tests.odoo_repo_mixin import FIXTURE_MODULE_PATH

DEMO_FILE_PATH = "demo/my_model.xml"
DEMO_MANIFEST_LINE = f'        "{DEMO_FILE_PATH}",\n'
MANIFEST_INSTALLABLE_TRUE = '    "installable": True,\n'
MANIFEST_INSTALLABLE_FALSE = '    "installable": False,\n'


class TestOdooModuleBranchData(Common):
    """Scan the git fixture repository and check the collected data elements."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Keep a reference on the original commit of the fixture module, to be
        # able to restore its state once a test modified it
        repo = git.Repo(cls.repo_upstream_path)
        repo.git.checkout(cls.branch1_name)
        cls.original_sha = repo.head.object.hexsha

    def setUp(self):
        super().setUp()
        self.addCleanup(self._restore_upstream_module)

    def _restore_upstream_module(self):
        """Restore the fixture module to its original state."""
        repo = git.Repo(self.repo_upstream_path)
        repo.git.checkout(self.branch1_name)
        repo.git.reset("--hard", self.original_sha)

    def _get_module_branch(self):
        module = self.env["odoo.module"].search([("name", "=", self.module_name)])
        return self.env["odoo.module.branch"].search(
            [("module_id", "=", module.id), ("branch_id", "=", self.branch.id)]
        )

    def _get_data(self, module_branch, xml_id):
        """Return the data record, archived records included."""
        return (
            self.env["odoo.module.branch.data"]
            .with_context(active_test=False)
            .search(
                [
                    ("module_branch_id", "=", module_branch.id),
                    ("xml_id", "=", xml_id),
                ]
            )
        )

    def _commit_upstream_module(self, message):
        """Commit the current changes of the fixture module."""
        repo = git.Repo(self.repo_upstream_path)
        repo.git.checkout(self.branch1_name)
        repo.git.add("-A", str(self.addon_path))
        repo.index.commit(message)

    def _remove_demo_file(self):
        """Remove the demo file from the fixture module."""
        manifest_path = self.addon_path / "__manifest__.py"
        content = manifest_path.read_text()
        content = content.replace(DEMO_MANIFEST_LINE, "")
        manifest_path.write_text(content)
        demo_path = self.addon_path / DEMO_FILE_PATH
        demo_path.unlink()
        self._commit_upstream_module("[REM] Remove demo data")

    def _restore_demo_file(self):
        """Restore the demo file removed by `_remove_demo_file`."""
        shutil.copy(
            FIXTURE_MODULE_PATH / "__manifest__.py",
            self.addon_path / "__manifest__.py",
        )
        demo_path = self.addon_path / DEMO_FILE_PATH
        demo_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIXTURE_MODULE_PATH / DEMO_FILE_PATH, demo_path)
        self._commit_upstream_module("[ADD] Restore demo data")

    def _set_installable(self, installable):
        """Update the 'installable' flag of the fixture module."""
        manifest_path = self.addon_path / "__manifest__.py"
        content = manifest_path.read_text()
        if installable:
            content = content.replace(
                MANIFEST_INSTALLABLE_FALSE, MANIFEST_INSTALLABLE_TRUE
            )
        else:
            content = content.replace(
                MANIFEST_INSTALLABLE_TRUE, MANIFEST_INSTALLABLE_FALSE
            )
        manifest_path.write_text(content)
        self._commit_upstream_module(f"[CHG] installable = {installable}")

    def test_scan_collects_code_and_data(self):
        """A scan collects the models and the data elements of the module."""
        self._run_odoo_repository_action_scan(self.branch.id)
        module_branch = self._get_module_branch()
        self.assertTrue(module_branch.installable)
        # Models
        self.assertEqual(module_branch.models_count, 2)
        my_model = module_branch.model_ids.filtered(
            lambda rec: rec.odoo_model_name == "my_module.my_model"
        )
        self.assertEqual(len(my_model.field_ids), 1)
        self.assertEqual(len(my_model.method_ids), 1)
        # Data elements (4 'data' + 1 'demo')
        self.assertEqual(module_branch.data_count, 5)
        # XML record (view)
        view = self._get_data(module_branch, "my_model_view_form")
        self.assertTrue(view.active)
        self.assertEqual(view.odoo_model_name, "ir.ui.view")
        self.assertEqual(view.name, "my_module.my_model.form")
        self.assertEqual(view.file_path, "views/my_model.xml")
        self.assertEqual(view.data_type, "data")
        self.assertTrue(view.loaded)
        self.assertFalse(view.noupdate)
        self.assertEqual(view.data["target_model"], "my_module.my_model")
        self.assertIn('"target_model": "my_module.my_model"', view.data_text)
        # XML record (menu)
        menu = self._get_data(module_branch, "my_model_menu")
        self.assertEqual(menu.odoo_model_name, "ir.ui.menu")
        self.assertEqual(menu.name, "My Model")
        # CSV record: no 'name' available, fallback on the XML id
        access = self._get_data(module_branch, "access_my_module_my_model")
        self.assertEqual(access.odoo_model_name, "ir.model.access")
        self.assertEqual(access.name, "access_my_module_my_model")
        self.assertEqual(access.file_path, "security/ir.model.access.csv")
        # Demo record
        demo = self._get_data(module_branch, "my_model_demo")
        self.assertEqual(demo.data_type, "demo")
        self.assertEqual(demo.odoo_model_name, "my_module.my_model")
        self.assertEqual(demo.name, "Demo")
        self.assertEqual(demo.file_path, "demo/my_model.xml")
        self.assertTrue(demo.noupdate)
        # The target models are registered for the current Odoo version
        for model_name in (
            "my_module.my_model",
            "res.partner",
            "ir.ui.view",
            "ir.ui.menu",
            "ir.model.access",
        ):
            model_version = self.env["odoo.model.version"].search(
                [
                    ("odoo_model_id.name", "=", model_name),
                    ("odoo_version_id", "=", self.branch.id),
                ]
            )
            self.assertTrue(model_version)

    def test_scan_data_to_dict(self):
        """Data are exported grouped by model, as done by the scanner."""
        self._run_odoo_repository_action_scan(self.branch.id)
        module_branch = self._get_module_branch()
        data = module_branch._to_dict()
        self.assertEqual(
            sorted(data["data"]),
            ["ir.model.access", "ir.ui.menu", "ir.ui.view", "res.partner"],
        )
        self.assertEqual(sorted(data["demo"]), ["my_module.my_model"])
        self.assertEqual(data["data"]["ir.ui.view"][0]["id"], "my_model_view_form")
        self.assertEqual(data["demo"]["my_module.my_model"][0]["id"], "my_model_demo")

    def test_scan_data_is_override(self):
        """Data overriding a record of another module is flagged."""
        self._run_odoo_repository_action_scan(self.branch.id)
        module_branch = self._get_module_branch()
        # A record overriding a record of another module is flagged
        override = self._get_data(module_branch, "base.main_partner")
        self.assertTrue(override.is_override)
        self.assertEqual(override.data_type, "data")
        # The overridden record doesn't exist yet ('base' module not scanned)
        self.assertFalse(override.overridden_id)
        # Records of the module itself are not flagged
        self.assertFalse(
            self._get_data(module_branch, "my_model_view_form").is_override
        )
        self.assertFalse(self._get_data(module_branch, "my_model_menu").is_override)
        # A fully qualified ID on the current module is not an override
        model_version = self.env["odoo.model.version"].search(
            [
                ("odoo_model_id.name", "=", "res.partner"),
                ("odoo_version_id", "=", self.branch.id),
            ]
        )
        record = self.env["odoo.module.branch.data"].create(
            {
                "module_branch_id": module_branch.id,
                "odoo_model_version_id": model_version.id,
                "xml_id": f"{self.module_name}.my_record",
                "name": "my_record",
                "data_type": "data",
            }
        )
        self.assertFalse(record.is_override)
        # Once the overridden record is scanned, the override targets it
        # ('base' module branch exists, created as a dependency of the scan)
        base_branch = self.env["odoo.module.branch"].search(
            [("module_id.name", "=", "base"), ("branch_id", "=", self.branch.id)]
        )
        original = self.env["odoo.module.branch.data"].create(
            {
                "module_branch_id": base_branch.id,
                "odoo_model_version_id": override.odoo_model_version_id.id,
                "xml_id": "main_partner",
                "name": "main_partner",
                "data_type": "data",
            }
        )
        override.invalidate_recordset(["overridden_id"])
        self.assertEqual(override.overridden_id, original)

    def test_scan_data_overridden_chain(self):
        """overridden_id hops through the chain of overriding modules."""
        self._run_odoo_repository_action_scan(self.branch.id)
        module_branch = self._get_module_branch()
        override = self._get_data(module_branch, "base.main_partner")
        base_branch = self.env["odoo.module.branch"].search(
            [("module_id.name", "=", "base"), ("branch_id", "=", self.branch.id)]
        )
        original = self.env["odoo.module.branch.data"].create(
            {
                "module_branch_id": base_branch.id,
                "odoo_model_version_id": override.odoo_model_version_id.id,
                "xml_id": "main_partner",
                "name": "main_partner",
                "data_type": "data",
            }
        )
        # Module A depends on my_module and overrides the same record
        module_a_branch = self._create_odoo_module_branch(
            self._create_odoo_module("module_a"),
            self.branch,
            dependency_ids=[(4, module_branch.id)],
        )
        override_a = self.env["odoo.module.branch.data"].create(
            {
                "module_branch_id": module_a_branch.id,
                "odoo_model_version_id": override.odoo_model_version_id.id,
                "xml_id": "base.main_partner",
                "name": "base.main_partner",
                "data_type": "data",
            }
        )
        # The previous definition of A is the override of my_module,
        # the closest ancestor redefining the same external ID
        self.assertEqual(override_a.overridden_id, override)
        # Module B depends on module A and overrides the same record again
        module_b_branch = self._create_odoo_module_branch(
            self._create_odoo_module("module_b"),
            self.branch,
            dependency_ids=[(4, module_a_branch.id)],
        )
        override_b = self.env["odoo.module.branch.data"].create(
            {
                "module_branch_id": module_b_branch.id,
                "odoo_model_version_id": override.odoo_model_version_id.id,
                "xml_id": "base.main_partner",
                "name": "base.main_partner",
                "data_type": "data",
            }
        )
        self.assertEqual(override_b.overridden_id, override_a)
        # The chain ends on the original record
        self.assertEqual(override.overridden_id, original)

    def test_open_data(self):
        self._run_odoo_repository_action_scan(self.branch.id)
        module_branch = self._get_module_branch()
        action = module_branch.open_data()
        self.assertEqual(action["domain"], [("id", "in", module_branch.data_ids.ids)])

    def test_scan_data_removed_is_archived(self):
        """Data removed from the module is archived on the next scan."""
        self._run_odoo_repository_action_scan(self.branch.id)
        module_branch = self._get_module_branch()
        self.assertEqual(module_branch.data_count, 5)
        # Remove the demo file from the module and re-scan
        self._remove_demo_file()
        self._run_odoo_repository_action_scan(self.branch.id, force=True)
        module_branch = self._get_module_branch()
        # The demo record is archived, the other data elements are untouched
        self.assertEqual(len(module_branch.data_ids), 4)
        demo = self._get_data(module_branch, "my_model_demo")
        self.assertEqual(len(demo), 1)
        self.assertFalse(demo.active)
        view = self._get_data(module_branch, "my_model_view_form")
        self.assertTrue(view.active)

    def test_scan_data_readded_is_reactivated(self):
        """Data re-added after removal reactivates the archived entry."""
        self._run_odoo_repository_action_scan(self.branch.id)
        module_branch = self._get_module_branch()
        demo = self._get_data(module_branch, "my_model_demo")
        self.assertTrue(demo.active)
        # Remove the demo file and re-scan: the record is archived
        self._remove_demo_file()
        self._run_odoo_repository_action_scan(self.branch.id, force=True)
        module_branch = self._get_module_branch()
        demo = self._get_data(module_branch, "my_model_demo")
        self.assertFalse(demo.active)
        # Restore the demo file and re-scan: the record is reactivated
        self._restore_demo_file()
        self._run_odoo_repository_action_scan(self.branch.id, force=True)
        module_branch = self._get_module_branch()
        # No duplicate record was created
        demo = (
            self.env["odoo.module.branch.data"]
            .with_context(active_test=False)
            .search(
                [
                    ("module_branch_id", "=", module_branch.id),
                    ("xml_id", "=", "my_model_demo"),
                ]
            )
        )
        self.assertEqual(len(demo), 1)
        self.assertTrue(demo.active)

    def test_scan_data_not_installable_is_cleaned(self):
        """Data are unlinked when the module is not installable."""
        self._run_odoo_repository_action_scan(self.branch.id)
        module_branch = self._get_module_branch()
        self.assertEqual(module_branch.data_count, 5)
        # Make the module not installable and re-scan
        self._set_installable(False)
        self._run_odoo_repository_action_scan(self.branch.id, force=True)
        module_branch = self._get_module_branch()
        self.assertFalse(module_branch.installable)
        self.assertFalse(module_branch.data_ids)
        self.assertFalse(module_branch.model_ids)
