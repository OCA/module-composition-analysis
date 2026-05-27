# Copyright 2024 Camptocamp SA
# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from .common import MigrationCommon


class TestOdooModuleBranch(MigrationCommon):
    def test_next_odoo_version_module_branch_id(self):
        """Test next_odoo_version_module_branch_id computed field."""
        # Create next branch module
        next_module_branch = self._create_odoo_module_branch(
            self.module,
            self.branch2,
            specific=False,
            repository_branch_id=self.repo_branch2.id,
            last_scanned_commit="sha",
        )
        # Test next_odoo_version_module_branch_id
        self.assertEqual(
            self.module_branch.next_odoo_version_module_branch_id, next_module_branch
        )

    def test_next_odoo_version_module_branch_id_with_renamed_module(self):
        """Test next_odoo_version_module_branch_id with renamed module."""
        # Create a new module name for the renamed module
        next_module = self.module.copy({"name": "next_module"})
        # Create next branch module with new name
        next_module_branch = self._create_odoo_module_branch(
            next_module,
            self.branch2,
            specific=False,
            repository_branch_id=self.repo_branch2.id,
            last_scanned_commit="sha",
        )
        # Add timeline entry for renaming
        self._create_timeline(self.module_branch, next_module, "renamed")
        # Test next_odoo_version_module_branch_id follows renaming
        self.assertEqual(
            self.module_branch.next_odoo_version_module_branch_id, next_module_branch
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
            "target_commit1",
            source=self.branch,
            target=self.branch2,
            report={"process": "migrate", "results": {}},
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
            "target_commit1",
            source=self.branch,
            target=self.branch2,
            report={"process": "migrate", "results": {}},
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
            repository_branch_id=self.repo_branch2.id,
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
            source=self.branch,
            target=self.branch2,
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
        self.assertEqual(
            self.module_branch.migration_ids.target_module_branch_id,
            target_module_branch,
        )
        self.assertTrue(self.module_branch.migration_ids.migration_scan)
        self.assertTrue(self.module_branch.migration_scan)
        # Simulate the migration scan.
        # The source module is fully ported and doesn't need a migration
        # scan afterwards.
        self._simulate_migration_scan(
            "target_commit2",
            source=self.branch,
            target=self.branch2,
            report={"results": {}},
        )
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
            "target_commit1",
            source=self.branch,
            target=self.branch2,
            report={"process": "migrate", "results": {}},
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
            "target_commit1",
            source=self.branch,
            target=self.branch2,
            report={"process": "migrate", "results": {}},
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
            "target_commit1",
            source=self.branch,
            target=self.branch2,
            report={"process": "migrate", "results": {}},
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

    def test_renamed_module(self):
        """Test migration data of a module renamed.

        Data input:
            - source version = X
            - target version = X+1
            - module renamed in X+1

        Expected ouput:
            - 'renamed_to_module_id' should target module renamed in X+1
        """
        self.odoo_repository.collect_migration_data = True
        # Next version is X+1
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
            repository_branch_id=self.repo_branch2.id,
            last_scanned_commit="sha",
        )
        # Generate migration data records from X to X+1
        self.env["odoo.migration.path"].create(
            {
                "source_branch_id": self.branch.id,
                "target_branch_id": next_branch.id,
            }
        )
        self._simulate_migration_scan(
            "target_commit1",
            source=self.branch,
            target=next_branch,
            report={"process": "migrate", "results": {}},
        )
        # Module has been renamed starting from X+1
        self._create_timeline(self.module_branch, new_module, "renamed")
        renamed_to_module = self.module_branch._renamed_to_module_in_target_version(
            next_branch
        )
        self.assertEqual(renamed_to_module, new_module)
        # We target X+2 to check if intermediate data in X+1 is found
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
        self.assertEqual(mig.state, "fully_ported")
        self.assertTrue(mig.migration_scan)

    def test_renamed_module_twice(self):
        """Test migration data of a module renamed twice.

        Data input:
            - source version = X
            - target version = X+2
            - module renamed in X+1
            - module renamed again in X+2

        Expected ouput:
            - 'renamed_to_module_id' should target module renamed in X+2
        """
        self.odoo_repository.collect_migration_data = True
        # Next version is X+1
        next_branch = self.env["odoo.branch"].search(
            [("sequence", "=", self.branch.sequence + 1)]
        )
        self.assertEqual(self.branch.next_id, next_branch)
        # Target version is X+2
        target_branch = self.env["odoo.branch"].search(
            [("sequence", "=", self.branch.sequence + 2)]
        )
        self.assertEqual(self.branch.next_id.next_id, target_branch)
        # Create the next module
        next_module = self.module.copy({"name": "next_module"})
        next_module_branch = self._create_odoo_module_branch(
            next_module,
            next_branch,
            specific=False,
            repository_branch_id=self.repo_branch2.id,
            last_scanned_commit="sha_next",
        )
        # Create the target module
        target_module = self.module.copy({"name": "target_module"})
        target_module_branch = self._create_odoo_module_branch(
            target_module,
            target_branch,
            specific=False,
            repository_branch_id=self.repo_branch3.id,
            last_scanned_commit="sha_target",
        )
        # Generate migration data records from X to X+2 (with a gap)
        self.env["odoo.migration.path"].create(
            {
                "source_branch_id": self.branch.id,
                "target_branch_id": target_branch.id,
            }
        )
        self._simulate_migration_scan(
            "target_commit1",
            source=self.branch,
            target=target_branch,
            report={"process": "migrate", "results": {}},
        )
        # Module has been renamed in X+1
        self._create_timeline(self.module_branch, next_module, "renamed")
        renamed_to_module = self.module_branch._renamed_to_module_in_target_version(
            next_branch
        )
        self.assertEqual(renamed_to_module, next_module)
        # Module has been renamed again in X+2
        self._create_timeline(next_module_branch, target_module, "renamed")
        renamed_to_module = next_module_branch._renamed_to_module_in_target_version(
            target_branch
        )
        self.assertEqual(renamed_to_module, target_module)
        # Check migration data
        mig = self.module_branch.migration_ids
        self.assertEqual(mig.renamed_to_module_id, target_module)
        self.assertFalse(mig.replaced_by_module_id)
        self.assertEqual(mig.target_module_branch_id, target_module_branch)
        self.assertFalse(mig.last_target_scanned_commit)
        self.assertEqual(mig.state, "fully_ported")
        self.assertTrue(mig.migration_scan)

    def test_replaced_module(self):
        """Test migration data of a module replaced.

        Data input:
            - source version = X
            - target version = X+1
            - module replaced in X+1

        Expected ouput:
            - 'replaced_by_module_id' should target module replaced in X+1
        """
        self.odoo_repository.collect_migration_data = True
        # Next version is X+1
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
            "target_commit1",
            source=self.branch,
            target=next_branch,
            report={"process": "migrate", "results": {}},
        )
        # New module is replacing current one starting from X+1
        self._create_timeline(self.module_branch, new_module, "replaced")
        replaced_by_module = self.module_branch._replaced_by_module_in_target_version(
            next_branch
        )
        self.assertEqual(replaced_by_module, new_module)
        # We target X+2 to check if intermediate data in X+1 is found
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
        # No migration scan needed for replaced modules
        self.assertFalse(mig.migration_scan)

    def test_replaced_module_twice(self):
        """Test migration data of a module replaced twice.

        Data input:
            - source version = X
            - target version = X+2
            - module replaced in X+1
            - module replaced again in X+2

        Expected ouput:
            - 'replaced_by_module_id' should target module replaced in X+2
        """
        self.odoo_repository.collect_migration_data = True
        # Next version is X+1
        next_branch = self.env["odoo.branch"].search(
            [("sequence", "=", self.branch.sequence + 1)]
        )
        self.assertEqual(self.branch.next_id, next_branch)
        # Target version is X+2
        target_branch = self.env["odoo.branch"].search(
            [("sequence", "=", self.branch.sequence + 2)]
        )
        self.assertEqual(self.branch.next_id.next_id, target_branch)
        # Create the next module
        next_module = self.module.copy({"name": "next_module"})
        next_module_branch = self._create_odoo_module_branch(
            next_module,
            next_branch,
            specific=False,
            repository_branch_id=self.repo_branch2.id,
            last_scanned_commit="sha_next",
        )
        # Create the target module
        target_module = self.module.copy({"name": "target_module"})
        target_module_branch = self._create_odoo_module_branch(
            target_module,
            target_branch,
            specific=False,
            repository_branch_id=self.repo_branch3.id,
            last_scanned_commit="sha_target",
        )
        # Generate migration data records from X to X+2 (with a gap)
        self.env["odoo.migration.path"].create(
            {
                "source_branch_id": self.branch.id,
                "target_branch_id": target_branch.id,
            }
        )
        self._simulate_migration_scan(
            "target_commit1",
            source=self.branch,
            target=target_branch,
            report={"process": "migrate", "results": {}},
        )
        # Module has been replaced in X+1
        self._create_timeline(self.module_branch, next_module, "replaced")
        replaced_by_module = self.module_branch._replaced_by_module_in_target_version(
            next_branch
        )
        self.assertEqual(replaced_by_module, next_module)
        # Module has been replaced again in X+2
        self._create_timeline(next_module_branch, target_module, "replaced")
        replaced_by_module = next_module_branch._replaced_by_module_in_target_version(
            target_branch
        )
        self.assertEqual(replaced_by_module, target_module)
        # Check migration data
        mig = self.module_branch.migration_ids
        self.assertEqual(mig.replaced_by_module_id, target_module)
        self.assertFalse(mig.renamed_to_module_id)
        self.assertEqual(mig.target_module_branch_id, target_module_branch)
        self.assertFalse(mig.last_target_scanned_commit)
        self.assertEqual(mig.state, "replaced")
        # No migration scan needed for replaced modules
        self.assertFalse(mig.migration_scan)

    def test_renamed_then_replaced_module(self):
        """Test migration data of a module renamed then replaced.

        Data input:
            - source version = X
            - target version = X+2
            - module renamed in X+1
            - module replaced in X+2

        Expected ouput:
            - 'renamed_to_module_id' should be empty
            - 'replaced_by_module_id' should target module replaced in X+2
        """
        self.odoo_repository.collect_migration_data = True
        # Next version is X+1
        next_branch = self.env["odoo.branch"].search(
            [("sequence", "=", self.branch.sequence + 1)]
        )
        self.assertEqual(self.branch.next_id, next_branch)
        # Target version is X+2
        target_branch = self.env["odoo.branch"].search(
            [("sequence", "=", self.branch.sequence + 2)]
        )
        self.assertEqual(self.branch.next_id.next_id, target_branch)
        # Create the next module
        next_module = self.module.copy({"name": "next_module"})
        next_module_branch = self._create_odoo_module_branch(
            next_module,
            next_branch,
            specific=False,
            repository_branch_id=self.repo_branch2.id,
            last_scanned_commit="sha_next",
        )
        # Create the target module
        target_module = self.module.copy({"name": "target_module"})
        target_module_branch = self._create_odoo_module_branch(
            target_module,
            target_branch,
            specific=False,
            repository_branch_id=self.repo_branch3.id,
            last_scanned_commit="sha_target",
        )
        # Generate migration data records from X to X+2 (with a gap)
        self.env["odoo.migration.path"].create(
            {
                "source_branch_id": self.branch.id,
                "target_branch_id": target_branch.id,
            }
        )
        self._simulate_migration_scan(
            "target_commit1",
            source=self.branch,
            target=target_branch,
            report={"process": "migrate", "results": {}},
        )
        # Module has been renamed in X+1
        self._create_timeline(self.module_branch, next_module, "renamed")
        renamed_to_module = self.module_branch._renamed_to_module_in_target_version(
            next_branch
        )
        self.assertEqual(renamed_to_module, next_module)
        # Module has been replaced in X+2
        self._create_timeline(next_module_branch, target_module, "replaced")
        replaced_by_module = next_module_branch._replaced_by_module_in_target_version(
            target_branch
        )
        self.assertEqual(replaced_by_module, target_module)
        # Check migration data
        mig = self.module_branch.migration_ids
        self.assertFalse(mig.renamed_to_module_id)
        self.assertEqual(mig.replaced_by_module_id, target_module)
        self.assertEqual(mig.target_module_branch_id, target_module_branch)
        self.assertFalse(mig.last_target_scanned_commit)
        self.assertEqual(mig.state, "replaced")
        self.assertFalse(mig.migration_scan)

    def test_replaced_then_renamed_module(self):
        """Test migration data of a module replaced then renamed.

        Data input:
            - source version = X
            - target version = X+2
            - module replaced in X+1
            - module renamed in X+2

        Expected ouput:
            - 'renamed_to_module_id' should be empty
            - 'replaced_by_module_id' should target module renamed in X+2
        """
        self.odoo_repository.collect_migration_data = True
        # Next version is X+1
        next_branch = self.env["odoo.branch"].search(
            [("sequence", "=", self.branch.sequence + 1)]
        )
        self.assertEqual(self.branch.next_id, next_branch)
        # Target version is X+2
        target_branch = self.env["odoo.branch"].search(
            [("sequence", "=", self.branch.sequence + 2)]
        )
        self.assertEqual(self.branch.next_id.next_id, target_branch)
        # Create the next module
        next_module = self.module.copy({"name": "next_module"})
        next_module_branch = self._create_odoo_module_branch(
            next_module,
            next_branch,
            specific=False,
            repository_branch_id=self.repo_branch2.id,
            last_scanned_commit="sha_next",
        )
        # Create the target module
        target_module = self.module.copy({"name": "target_module"})
        target_module_branch = self._create_odoo_module_branch(
            target_module,
            target_branch,
            specific=False,
            repository_branch_id=self.repo_branch3.id,
            last_scanned_commit="sha_target",
        )
        # Generate migration data records from X to X+2 (with a gap)
        self.env["odoo.migration.path"].create(
            {
                "source_branch_id": self.branch.id,
                "target_branch_id": target_branch.id,
            }
        )
        self._simulate_migration_scan(
            "target_commit1",
            source=self.branch,
            target=target_branch,
            report={"process": "migrate", "results": {}},
        )
        # Module has been replaced in X+1
        self._create_timeline(self.module_branch, next_module, "replaced")
        replaced_by_module = self.module_branch._replaced_by_module_in_target_version(
            next_branch
        )
        self.assertEqual(replaced_by_module, next_module)
        # Module has been renamed in X+2
        self._create_timeline(next_module_branch, target_module, "renamed")
        renamed_to_module = next_module_branch._renamed_to_module_in_target_version(
            target_branch
        )
        self.assertEqual(renamed_to_module, target_module)
        # Check migration data
        mig = self.module_branch.migration_ids
        self.assertFalse(mig.renamed_to_module_id)
        self.assertEqual(mig.replaced_by_module_id, target_module)
        self.assertEqual(mig.target_module_branch_id, target_module_branch)
        self.assertFalse(mig.last_target_scanned_commit)
        self.assertEqual(mig.state, "replaced")
        self.assertFalse(mig.migration_scan)
