# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields

from .common import Common


class TestOdooRepositoryScan(Common):
    def test_check_config(self):
        self.odoo_repository._check_config()

    def test_action_scan_basic(self):
        """Test the creation of a module when scanning a (generic) repository."""
        self.assertFalse(self.odoo_repository.specific)
        module = self.env["odoo.module"].search([("name", "=", self.module_name)])
        self.assertFalse(module)
        self._run_odoo_repository_action_scan(self.branch.id)
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
        self.assertFalse(module_branch.specific)
        self.assertEqual(module_branch.dependency_ids.module_name, "base")
        self.assertFalse(module_branch.dependency_ids.specific)
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

    def test_action_scan_repo_specific(self):
        """Test the creation of a module when scanning a specific repository."""
        self.odoo_repository.specific = True
        self.odoo_repository.write(
            {
                "specific": True,
                "branch_ids": [
                    fields.Command.create({"branch_id": self.branch.id}),
                ],
            }
        )
        self.assertTrue(self.odoo_repository.specific)
        self._run_odoo_repository_action_scan(self.branch.id)
        # Check module data
        module = self.env["odoo.module"].search([("name", "=", self.module_name)])
        module_branch = self.env["odoo.module.branch"].search(
            [("module_id", "=", module.id), ("branch_id", "=", self.branch.id)]
        )
        self.assertTrue(module_branch.specific)
        self.assertFalse(module_branch.dependency_ids.specific)

    def test_action_scan_repo_module_exists(self):
        """Test the update of existing module when scanning a repository.

        If a module has already been scanned in the current repository, a second
        scan will trigger an update of its data.
        """
        # First scan, like in `test_action_scan_first_time`
        self._run_odoo_repository_action_scan(self.branch.id)
        module = self.env["odoo.module"].search([("name", "=", self.module_name)])
        module_branch = self.env["odoo.module.branch"].search(
            [("module_id", "=", module.id), ("branch_id", "=", self.branch.id)]
        )
        # Change some data in the module before triggering the second scan
        module_branch.write({"title": False})
        # Launch a second scan (force it to make it happen)
        self._run_odoo_repository_action_scan(self.branch.id, force=True)
        self.assertEqual(module_branch.title, "Test")

    def test_action_scan_orphaned_module_exists(self):
        """Test the link of an orphaned module when scanning a repository.

        An orphaned module is a record without repository assigned while we know
        its name and branch. Such record is automatically created when generating
        dependencies of a given module that have not been scanned yet, or by
        importing installed modules in a project (see `odoo_project` Odoo module).

        If such a module matches a module scanned in a repository, it is updated
        accordingly to belong to this repository.
        """
        # Create an orphaned module.
        # To ease its creation, we run a scan to get the record created, and
        # we update it to make it orphaned.
        self._run_odoo_repository_action_scan(self.branch.id)
        module = self.env["odoo.module"].search([("name", "=", self.module_name)])
        module_branch = self.env["odoo.module.branch"].search(
            [("module_id", "=", module.id), ("branch_id", "=", self.branch.id)]
        )
        module_branch.write(
            {
                "repository_branch_id": False,
                "last_scanned_commit": False,
                "dependency_ids": False,
                "version_ids": False,
            }
        )
        # Launch a scan
        self._run_odoo_repository_action_scan(self.branch.id, force=True)
        self.assertEqual(module_branch.repository_id, self.odoo_repository)

    def _create_wrong_repo_branch(self, repo_sequence=100):
        wrong_repo = self.env["odoo.repository"].create(
            {
                "org_id": self.odoo_repository.org_id.id,
                "name": "wrong_repo",
                "repo_url": "https://example.net/OCA-test/wrong_repo",
                "clone_url": "https://example.net/OCA-test/wrong_repo",
                "repo_type": "github",
                "sequence": repo_sequence,
            }
        )
        wrong_repo_branch = self.env["odoo.repository.branch"].create(
            {
                "repository_id": wrong_repo.id,
                "branch_id": self.branch.id,
            }
        )
        return wrong_repo_branch

    def _create_unmerged_module_branch(self):
        # To ease the creation of such module, we run a scan to get the record
        # created, and we update it to make it unmerged/pending.
        self._run_odoo_repository_action_scan(self.branch.id)
        module = self.env["odoo.module"].search([("name", "=", self.module_name)])
        module_branch = self.env["odoo.module.branch"].search(
            [("module_id", "=", module.id), ("branch_id", "=", self.branch.id)]
        )
        wrong_repo_branch = self._create_wrong_repo_branch(
            # Lower priority than self.odoo_repository
            repo_sequence=200
        )
        wrong_repo = wrong_repo_branch.repository_id
        module_branch.write(
            {
                "repository_branch_id": wrong_repo_branch,
                "last_scanned_commit": False,
                "dependency_ids": False,
                "version_ids": False,
                "pr_url": f"{wrong_repo.repo_url}/pull/1",
                "specific": False,
            }
        )
        return module_branch

    def test_action_scan_repo_generic_unmerged_module_exists(self):
        """Test link of an unmerged module when scanning a generic repository.

        An unmerged module is like an orphaned module but with a PR attached.
        However such PR indicates from which repository a module is coming from,
        but this information could also be wrong (wrong PR detected on the wrong
        repository).

        Note: unmerged modules can only be generic, as PR detection is restricted
        only to generic modules.

        When scanning a generic repository, if an unmerged module is
        detected it should be linked to this scanned repository.
        """
        self.odoo_repository.specific = False
        # Create an unmerged module
        module_branch = self._create_unmerged_module_branch()
        self.assertFalse(module_branch.specific)
        self.assertNotEqual(module_branch.repository_id, self.odoo_repository)
        # Launch a scan
        self._run_odoo_repository_action_scan(self.branch.id, force=True)
        self.assertFalse(module_branch.specific)
        self.assertEqual(module_branch.repository_id, self.odoo_repository)

    def test_action_scan_repo_specific_unmerged_module_exists(self):
        """Test non-link of an unmerged module when scanning a specific repository.

        When scanning a specific repository, detection of unmerged modules is
        not done as such modules are linked to generic repositories only.
        """
        self.odoo_repository.specific = True
        # Create an unmerged module
        module_branch = self._create_unmerged_module_branch()
        self.assertFalse(module_branch.specific)
        self.assertNotEqual(module_branch.repository_id, self.odoo_repository)
        # Launch a scan
        self._run_odoo_repository_action_scan(self.branch.id, force=True)
        # Unmerged module hasn't been attached to the scanned repository
        self.assertNotEqual(module_branch.repository_id, self.odoo_repository)

    def test_action_scan_uninstallable_module(self):
        """Test scan of an 'installable: False' module.

        Such module should not be created with its dependencies (Odoo, Python...)
        or versions history to not pollute the DB. Such data could be
        outdated as the module is flagged as not installable. They will be updated
        once the module is migrated/installable.
        """
        self._update_module_installable_on_branch(self.branch.name, installable=False)
        module = self.env["odoo.module"].search([("name", "=", self.module_name)])
        self.assertFalse(module)
        self._run_odoo_repository_action_scan(self.branch.id)
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
        self.assertFalse(module_branch.specific)
        # No dependencies
        self.assertFalse(module_branch.dependency_ids)
        self.assertFalse(module_branch.external_dependencies)
        self.assertFalse(module_branch.python_dependency_ids)
        # No version scanned
        self.assertFalse(module_branch.version_ids)
