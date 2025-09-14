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
        self.std_repository = self.env.ref("odoo_repository.odoo_repository_odoo_odoo")
        self.oca_repository = self.env.ref("odoo_repository.repo_oca_server_tools")
        self.gen_repository = self.env["odoo.repository"].create(
            {
                "name": "new_repo",
                "org_id": self.odoo_repository.org_id.id,
                "repo_url": "http://example.net/new_repo",
                "specific": False,
                "to_scan": False,
            }
        )
        self.gen_repository.addons_path_ids = self.odoo_repository.addons_path_ids

    def _simulate_migration_scan(self, target_commit, report=None):
        """Helper method that pushes scanned migration data."""
        data = {
            "module": self.module_branch.module_name,
            "source_version": self.branch.name,
            "source_branch": self.branch.name,
            "target_version": self.branch2.name,
            "target_branch": self.branch2.name,
            "source_commit": self.module_branch.last_scanned_commit,
            "target_commit": target_commit,
        }
        if report is not None:
            data["report"] = report
        return self.env["odoo.module.branch.migration"].push_scanned_data(
            self.module_branch.id,
            data,
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
        self.assertFalse(self.module_branch.migration_ids)
        self.assertFalse(self.module_branch.migration_scan)
        self.odoo_repository.collect_migration_data = True
        self.assertFalse(self.module_branch.migration_ids)
        self.assertTrue(self.module_branch.migration_scan)

    def test_migration_scan_missing_migration_path(self):
        self.odoo_repository.collect_migration_data = True
        self.assertFalse(self.module_branch.migration_ids)
        self.assertFalse(self.module_branch.migration_scan)
        self.env["odoo.migration.path"].create(
            {
                "source_branch_id": self.branch.id,
                "target_branch_id": self.branch2.id,
            }
        )
        self.assertFalse(self.module_branch.migration_ids)
        self.assertTrue(self.module_branch.migration_scan)
        # Once we collected migration data for the expected branch+commit
        # the module doesn't require a migration scan anymore
        self._simulate_migration_scan(
            "target_commit1", report={"process": "migrate", "results": {}}
        )
        self.assertTrue(self.module_branch.migration_ids)
        self.assertFalse(self.module_branch.migration_scan)

    def test_migration_scan_target_module_in_review_then_merged(self):
        """Test full flow of the migration of a module.

        1) At first, the module of the source branch needs a migration scan
           because the migration data are missing for the target branch.
        2) Once the migration is done (and migration data available), the migration
           scan is not needed anymore.
        3) Then the target module could be found in a PR to review, but this
           doesn't
        """
        self.odoo_repository.collect_migration_data = True
        # Simulate a scan of a given migration path while the target module is
        # not yet migrated/available in a repository
        self.assertFalse(self.module_branch.migration_ids)
        self.assertFalse(self.module_branch.migration_scan)
        self.env["odoo.migration.path"].create(
            {
                "source_branch_id": self.branch.id,
                "target_branch_id": self.branch2.id,
            }
        )
        self.assertFalse(self.module_branch.migration_ids)
        self.assertTrue(self.module_branch.migration_scan)
        self._simulate_migration_scan(
            "target_commit1", report={"process": "migrate", "results": {}}
        )
        self.assertTrue(self.module_branch.migration_ids)
        self.assertFalse(self.module_branch.migration_ids.migration_scan)
        self.assertFalse(self.module_branch.migration_scan)
        self.assertEqual(self.module_branch.migration_ids.state, "migrate")
        # Make the module available for targeted branch in review (available in a PR).
        # The source module now needs a migration scan as the target module is
        # available in a PR, the migration status has to be updated.
        target_module_branch = self._create_odoo_module_branch(
            self.module,
            self.branch2,
            specific=False,
            repository_branch_id=self.repo_branch.id,
            # Module available in a PR
            pr_url="https://my/pr",
        )
        self.assertEqual(
            self.module_branch.migration_ids.target_module_branch_id,
            target_module_branch,
        )
        self.assertEqual(self.module_branch.migration_ids.state, "migrate")
        self.assertTrue(self.module_branch.migration_ids.migration_scan)
        self.assertTrue(self.module_branch.migration_scan)
        # Simulate the migration scan.
        # The source module doesn't need a migration scan anymore.
        self._simulate_migration_scan(
            "target_commit1",
            report={
                "process": "migrate",
                "results": {"existing_pr": {"url": target_module_branch.pr_url}},
            },
        )
        self.assertEqual(self.module_branch.migration_ids.state, "review_migration")
        self.assertFalse(self.module_branch.migration_ids.migration_scan)
        self.assertFalse(self.module_branch.migration_scan)
        # Merge the module in the upstream repository.
        # The source module now needs a migration scan (to check if there is
        # something to port, or to set the module as fully ported...).
        target_module_branch.write(
            {
                "last_scanned_commit": "target_commit2",
                # When 'pr_url' is unset, this means the module has been merged
                "pr_url": False,
            }
        )
        self.module_branch.migration_ids.last_target_scanned_commit = (
            target_module_branch.last_scanned_commit
        )
        self.assertEqual(
            self.module_branch.migration_ids.target_module_branch_id,
            target_module_branch,
        )
        self.assertTrue(self.module_branch.migration_ids.migration_scan)
        self.assertTrue(self.module_branch.migration_scan)
        # Simulate the migration scan.
        # The source module is fully ported and doesn't need a migration scan afterwards.
        self._simulate_migration_scan("target_commit2", report={"results": {}})
        self.assertEqual(self.module_branch.migration_ids.state, "fully_ported")
        self.assertFalse(self.module_branch.migration_ids.migration_scan)
        self.assertFalse(self.module_branch.migration_scan)

    def test_migration_scan_target_module_moved_to_standard(self):
        """Module moved into a standard repository."""
        # Simulate a scan of a given migration path while the target module is
        # not yet migrated/available in a repository
        self.env["odoo.migration.path"].create(
            {
                "source_branch_id": self.branch.id,
                "target_branch_id": self.branch2.id,
            }
        )
        self._simulate_migration_scan(
            "target_commit1", report={"process": "migrate", "results": {}}
        )
        self.assertTrue(self.module_branch.migration_ids)
        mig = self.module_branch.migration_ids
        self.assertFalse(mig.target_module_branch_id)
        self.assertFalse(mig.migration_scan)
        self.assertFalse(self.module_branch.migration_scan)
        self.assertEqual(mig.state, "migrate")
        # Then the module is discovered in a std repository
        std_repo_branch = self._create_odoo_repository_branch(
            self.std_repository, self.branch2
        )
        target_module_branch = self._create_odoo_module_branch(
            self.module,
            self.branch2,
            specific=False,
            is_standard=True,
            repository_branch_id=std_repo_branch.id,
        )
        self.assertEqual(mig.target_module_branch_id, target_module_branch)
        self.assertTrue(mig.moved_to_standard)
        self.assertFalse(mig.moved_to_oca)
        self.assertFalse(mig.moved_to_generic)
        self.assertEqual(mig.state, "moved_to_standard")
        self.assertFalse(mig.migration_scan)

    def test_migration_scan_target_module_moved_to_oca(self):
        """Module moved into an OCA repository."""
        # Simulate a scan of a given migration path while the target module is
        # not yet migrated/available in a repository
        self.env["odoo.migration.path"].create(
            {
                "source_branch_id": self.branch.id,
                "target_branch_id": self.branch2.id,
            }
        )
        self._simulate_migration_scan(
            "target_commit1", report={"process": "migrate", "results": {}}
        )
        self.assertTrue(self.module_branch.migration_ids)
        mig = self.module_branch.migration_ids
        self.assertFalse(mig.target_module_branch_id)
        self.assertFalse(mig.migration_scan)
        self.assertFalse(self.module_branch.migration_scan)
        self.assertEqual(mig.state, "migrate")
        # Then the module is discovered in an OCA repository
        oca_repo_branch = self._create_odoo_repository_branch(
            self.oca_repository, self.branch2
        )
        target_module_branch = self._create_odoo_module_branch(
            self.module,
            self.branch2,
            specific=False,
            repository_branch_id=oca_repo_branch.id,
        )
        self.assertEqual(mig.target_module_branch_id, target_module_branch)
        self.assertFalse(mig.moved_to_standard)
        self.assertTrue(mig.moved_to_oca)
        self.assertFalse(mig.moved_to_generic)
        self.assertEqual(mig.state, "moved_to_oca")
        self.assertFalse(mig.migration_scan)

    def test_migration_scan_target_module_moved_to_generic(self):
        """Specific module moved into a generic repository (that is not std or OCA)."""
        self.odoo_repository.specific = True
        # Simulate a scan of a given migration path while the target module is
        # not yet migrated/available in a repository
        self.env["odoo.migration.path"].create(
            {
                "source_branch_id": self.branch.id,
                "target_branch_id": self.branch2.id,
            }
        )
        self._simulate_migration_scan(
            "target_commit1", report={"process": "migrate", "results": {}}
        )
        self.assertTrue(self.module_branch.migration_ids)
        mig = self.module_branch.migration_ids
        self.assertFalse(mig.target_module_branch_id)
        self.assertFalse(mig.migration_scan)
        self.assertFalse(self.module_branch.migration_scan)
        self.assertEqual(mig.state, "migrate")
        # Then the module is discovered in an OCA repository
        gen_repo_branch = self._create_odoo_repository_branch(
            self.gen_repository, self.branch2
        )
        target_module_branch = self._create_odoo_module_branch(
            self.module,
            self.branch2,
            specific=False,
            repository_branch_id=gen_repo_branch.id,
        )
        self.assertEqual(mig.target_module_branch_id, target_module_branch)
        self.assertFalse(mig.moved_to_standard)
        self.assertFalse(mig.moved_to_oca)
        self.assertTrue(mig.moved_to_generic)
        self.assertEqual(mig.state, "moved_to_generic")
        self.assertFalse(mig.migration_scan)

    def test_renamed_to_module_in_target_version(self):
        self.odoo_repository.collect_migration_data = True
        # Next version is 16.0
        next_branch = self.env["odoo.branch"].search(
            [("sequence", "=", self.branch.sequence + 1)]
        )
        self.assertEqual(self.branch.next_id, next_branch)
        # Create the target module
        new_module = self.module.copy({"name": "new_module"})
        target_module_branch = self._create_odoo_module_branch(
            new_module,
            next_branch,
            specific=False,
            repository_branch_id=self.repo_branch.id,
            last_scanned_commit="sha",
        )
        # Generate migration data records
        self.env["odoo.migration.path"].create(
            {
                "source_branch_id": self.branch.id,
                "target_branch_id": next_branch.id,
            }
        )
        self._simulate_migration_scan(
            "target_commit1", report={"process": "migrate", "results": {}}
        )
        # Module has been renamed starting from 16.0
        self.module_branch.timeline_ids.create(
            {
                "module_branch_id": self.module_branch.id,
                "state": "renamed",
                "next_module_id": new_module.id,
            }
        )
        renamed_to_module = self.module_branch._renamed_to_module_in_target_version(
            next_branch
        )
        self.assertEqual(renamed_to_module, new_module)
        # We target 17.0 to check if intermediate data in 16.0 is found
        target_branch = self.env["odoo.branch"].search(
            [("sequence", "=", self.branch.sequence + 2)]
        )
        renamed_to_module = self.module_branch._renamed_to_module_in_target_version(
            target_branch
        )
        self.assertEqual(renamed_to_module, new_module)
        # Check migration data
        mig = self.module_branch.migration_ids
        self.assertEqual(mig.renamed_to_module_id, new_module)
        self.assertFalse(mig.replaced_by_module_id)
        self.assertEqual(mig.target_module_branch_id, target_module_branch)
        self.assertFalse(mig.last_target_scanned_commit)
        self.assertEqual(mig.state, "migrate")
        self.assertTrue(mig.migration_scan)

    def test_replaced_by_module_in_target_version(self):
        self.odoo_repository.collect_migration_data = True
        # Next version is 16.0
        next_branch = self.env["odoo.branch"].search(
            [("sequence", "=", self.branch.sequence + 1)]
        )
        self.assertEqual(self.branch.next_id, next_branch)
        # Create the target module
        new_module = self.module.copy({"name": "new_module"})
        target_module_branch = self._create_odoo_module_branch(
            new_module,
            next_branch,
            specific=False,
            repository_branch_id=self.repo_branch.id,
            last_scanned_commit="sha",
        )
        # Generate migration data records
        self.env["odoo.migration.path"].create(
            {
                "source_branch_id": self.branch.id,
                "target_branch_id": next_branch.id,
            }
        )
        self._simulate_migration_scan(
            "target_commit1", report={"process": "migrate", "results": {}}
        )
        # New module is replacing current one starting from 16.0
        self.module_branch.timeline_ids.create(
            {
                "module_branch_id": self.module_branch.id,
                "state": "replaced",
                "next_module_id": new_module.id,
            }
        )
        replaced_by_module = self.module_branch._replaced_by_module_in_target_version(
            next_branch
        )
        self.assertEqual(replaced_by_module, new_module)
        # We target 17.0 to check if intermediate data in 16.0 is found
        target_branch = self.env["odoo.branch"].search(
            [("sequence", "=", self.branch.sequence + 2)]
        )
        replaced_by_module = self.module_branch._replaced_by_module_in_target_version(
            target_branch
        )
        self.assertEqual(replaced_by_module, new_module)
        # Check migration data
        mig = self.module_branch.migration_ids
        self.assertEqual(mig.replaced_by_module_id, new_module)
        self.assertFalse(mig.renamed_to_module_id)
        self.assertEqual(mig.target_module_branch_id, target_module_branch)
        self.assertFalse(mig.last_target_scanned_commit)
        self.assertEqual(mig.state, "replaced")
        self.assertFalse(mig.migration_scan)
