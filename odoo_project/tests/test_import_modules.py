# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from .common import Common


class TestImportModules(Common):
    def test_import_modules_names(self):
        mod1 = "test1"
        mod2 = "test2"
        # Ensure these modules don't exist
        existing_mods = self.module_branch_model.search(
            [("module_name", "in", [mod1, mod2])]
        )
        self.assertFalse(existing_mods)
        # Import them through the wizard
        modules_list_text = f"{mod1}\n{mod2}"
        self._run_import_modules(self.project, modules_list_text)
        # They now exists as orphaned modules and are linked to the project
        existing_mods = self.module_branch_model.search(
            [
                ("module_name", "in", [mod1, mod2]),
                ("repository_id", "=", False),
                ("odoo_project_ids", "=", self.project.id),
            ]
        )
        self.assertEqual(len(existing_mods), 2)
        # Project modules are also created
        self.assertEqual(len(existing_mods.odoo_project_module_ids), 2)

    def test_import_modules_names_versions(self):
        mod1 = "test1"
        mod2 = "test2"
        # Ensure these modules don't exist
        existing_mods = self.module_branch_model.search(
            [("module_name", "in", [mod1, mod2])]
        )
        self.assertFalse(existing_mods)
        # Import them through the wizard with their installed versions
        modules_list_text = f"{mod1} 1.0.0\n{mod2} {self.branch}.1.0.0"
        self._run_import_modules(self.project, modules_list_text)
        # They now exists as orphaned modules and are linked to the project
        existing_mods = self.module_branch_model.search(
            [
                ("module_name", "in", [mod1, mod2]),
                ("repository_id", "=", False),
                ("odoo_project_ids", "=", self.project.id),
            ]
        )
        self.assertEqual(len(existing_mods), 2)
        # Project modules are also created
        self.assertEqual(len(existing_mods.odoo_project_module_ids), 2)
        pm1 = existing_mods.odoo_project_module_ids.filtered(
            lambda m: m.module_name == mod1
        )
        self.assertEqual(pm1.installed_version, "1.0.0")
        pm2 = existing_mods.odoo_project_module_ids.filtered(
            lambda m: m.module_name == mod2
        )
        self.assertEqual(pm2.installed_version, f"{self.branch}.1.0.0")

    def test_match_blacklisted_module(self):
        mod1 = "test1"
        mod2 = "test2"
        mod1_blacklisted = self.wiz_model._get_module(mod1)
        mod1_blacklisted.blacklisted = True
        # Import them through the wizard
        modules_list_text = f"{mod1}\n{mod2}"
        self._run_import_modules(self.project, modules_list_text)
        # Only one module has been imported as an orphaned module
        existing_mods = self.module_branch_model.search(
            [
                ("module_name", "in", [mod1, mod2]),
                ("repository_id", "=", False),
                ("odoo_project_ids", "=", self.project.id),
            ]
        )
        self.assertEqual(len(existing_mods), 1)
        # Project modules are also created
        self.assertEqual(len(existing_mods.odoo_project_module_ids), 1)

    def test_match_orphaned_module(self):
        mod1 = "test1"
        mod2 = "test2"
        mod1_orphaned = self.wiz_model._get_module(mod1)
        mod1_branch_orphaned = self.module_branch_model._create_orphaned_module_branch(
            self.branch, mod1_orphaned
        )
        # Import them through the wizard
        modules_list_text = f"{mod1}\n{mod2}"
        self._run_import_modules(self.project, modules_list_text)
        # They now exists as orphaned modules and are linked to the project
        existing_mods = self.module_branch_model.search(
            [
                ("module_name", "in", [mod1, mod2]),
                ("repository_id", "=", False),
                ("odoo_project_ids", "=", self.project.id),
            ]
        )
        self.assertEqual(len(existing_mods), 2)
        # One of them matched the existing orphaned module
        self.assertIn(mod1_branch_orphaned, existing_mods)
        # Project modules are also created
        self.assertEqual(len(existing_mods.odoo_project_module_ids), 2)

    def test_match_generic_module(self):
        mod1 = "test1"
        mod2 = "test2"
        mod1_generic = self.wiz_model._get_module(mod1)
        repo_branch = self._create_odoo_repository_branch(
            self.odoo_repository, self.branch
        )
        mod1_branch_generic = self._create_odoo_module_branch(
            mod1_generic,
            self.branch,
            specific=False,
            repository_branch_id=repo_branch.id,
        )
        # Import them through the wizard
        modules_list_text = f"{mod1}\n{mod2}"
        self._run_import_modules(self.project, modules_list_text)
        # They now exists and are linked to the project
        existing_mods = self.module_branch_model.search(
            [
                ("module_name", "in", [mod1, mod2]),
                ("odoo_project_ids", "=", self.project.id),
            ]
        )
        self.assertEqual(len(existing_mods), 2)
        # One of them matched the existing generic module
        self.assertIn(mod1_branch_generic, existing_mods)
        # Project modules are also created
        self.assertEqual(len(existing_mods.odoo_project_module_ids), 2)

    def test_match_project_repo_module(self):
        # Assign a repository to the project
        self.project.repository_id = self.odoo_repository
        self.project.odoo_version_id = self.branch
        mod1 = "test1"
        mod2 = "test2"
        mod1_in_repo = self.wiz_model._get_module(mod1)
        repo_branch = self._create_odoo_repository_branch(
            self.odoo_repository, self.branch
        )
        mod1_branch_in_repo = self._create_odoo_module_branch(
            mod1_in_repo,
            self.branch,
            specific=True,
            repository_branch_id=repo_branch.id,
        )
        # Import them through the wizard
        modules_list_text = f"{mod1}\n{mod2}"
        self._run_import_modules(self.project, modules_list_text)
        # They now exists and are linked to the project
        existing_mods = self.module_branch_model.search(
            [
                ("module_name", "in", [mod1, mod2]),
                ("odoo_project_ids", "=", self.project.id),
            ]
        )
        self.assertEqual(len(existing_mods), 2)
        # One of them matched the existing module hosted in project repository
        self.assertIn(mod1_branch_in_repo, existing_mods)
        # Project modules are also created
        self.assertEqual(len(existing_mods.odoo_project_module_ids), 2)
