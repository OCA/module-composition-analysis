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
        # Data elements (3 'data' + 1 'demo')
        self.assertEqual(module_branch.data_count, 4)
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
            sorted(data["data"]), ["ir.model.access", "ir.ui.menu", "ir.ui.view"]
        )
        self.assertEqual(sorted(data["demo"]), ["my_module.my_model"])
        self.assertEqual(data["data"]["ir.ui.view"][0]["id"], "my_model_view_form")
        self.assertEqual(data["demo"]["my_module.my_model"][0]["id"], "my_model_demo")

    def test_open_data(self):
        self._run_odoo_repository_action_scan(self.branch.id)
        module_branch = self._get_module_branch()
        action = module_branch.open_data()
        self.assertEqual(action["domain"], [("id", "in", module_branch.data_ids.ids)])

    def test_scan_data_removed_is_archived(self):
        """Data removed from the module is archived on the next scan."""
        self._run_odoo_repository_action_scan(self.branch.id)
        module_branch = self._get_module_branch()
        self.assertEqual(module_branch.data_count, 4)
        # Remove the demo file from the module and re-scan
        self._remove_demo_file()
        self._run_odoo_repository_action_scan(self.branch.id, force=True)
        module_branch = self._get_module_branch()
        # The demo record is archived, the other data elements are untouched
        self.assertEqual(len(module_branch.data_ids), 3)
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
        self.assertEqual(module_branch.data_count, 4)
        # Make the module not installable and re-scan
        self._set_installable(False)
        self._run_odoo_repository_action_scan(self.branch.id, force=True)
        module_branch = self._get_module_branch()
        self.assertFalse(module_branch.installable)
        self.assertFalse(module_branch.data_ids)
        self.assertFalse(module_branch.model_ids)
