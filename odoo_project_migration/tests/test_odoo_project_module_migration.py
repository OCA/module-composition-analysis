# Copyright 2026  Akretion (https://www.akretion.com).
# @author Sébastien Alix <sebastien.alix@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from .common import ProjectMigrationCommon


class TestOdooProjectModuleMigration(ProjectMigrationCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Import/install a module in our project
        cls._run_import_modules(cls.project, cls.module_branch.module_name)
        # Get current/next/target branches (N, N+1 and N+2)
        cls.current_branch = cls.project.odoo_version_id
        cls.next_branch = cls.current_branch.next_id
        cls.target_branch = cls.next_branch.next_id
        # Generate migration path from X to X+1
        cls.migration_path = cls.env["odoo.migration.path"].create(
            {
                "source_branch_id": cls.current_branch.id,
                "target_branch_id": cls.target_branch.id,
            }
        )

    def test_renamed_module_wo_migration_data(self):
        """Test project migration data of a module renamed, w/o collected mig data.

        Project migration data should show relevant data even if
        'collect_migration_data' option is disabled on scanned repositories.
        Such data could be updated thanks to timelines for instance, even if
        there is no underlying migration data record.

        Data input:
            - source version = X
            - target version = X+2
            - module renamed in X+1

        Expected ouput:
            - 'renamed_to_module_id' should target module renamed in X+1
            - migration 'state' should be 'available'
        """
        # Create the next module
        # /!\ We do not create the target module branch on X+2 on purpose,
        # so the project migration record cannot find a matching module.
        next_module = self.module.copy({"name": "next_module"})
        self._create_odoo_module_branch(
            next_module,
            self.next_branch,
            specific=False,
            repository_branch_id=self.repo_branch2.id,
            last_scanned_commit="sha1",
        )
        # Generate project_migration data records from X to X+2 (with a gap)
        self._generate_migration_data(self.project, self.migration_path)
        self.assertTrue(self.project.module_migration_ids)
        # Module has been renamed starting from X+1
        self._create_timeline(self.module_branch, next_module, "renamed")
        # Check migration data
        mig = self.project.module_migration_ids
        self.assertEqual(mig.renamed_to_module_id, next_module)
        self.assertFalse(mig.replaced_by_module_id)
        self.assertFalse(mig.target_module_branch_id)
        self.assertEqual(mig.state, "migrate")
        # Now we create the target module branch on X+2, the project migration
        # data should consider it
        target_module_branch = self._create_odoo_module_branch(
            next_module,
            self.target_branch,
            specific=False,
            repository_branch_id=self.repo_branch3.id,
            last_scanned_commit="sha2",
        )
        self.assertEqual(mig.target_module_branch_id, target_module_branch)
        self.assertEqual(mig.state, "available")

    def test_renamed_module_twice_wo_migration_data(self):
        """Test project mig data of a module renamed twice, w/o collected mig data.

        Project migration data should show relevant data even if
        'collect_migration_data' option is disabled on scanned repositories.
        Such data could be updated thanks to timelines for instance, even if
        there is no underlying migration data record.

        Data input:
            - source version = X
            - target version = X+2
            - module renamed in X+1
            - module renamed again in X+2

        Expected ouput:
            - 'renamed_to_module_id' should target module renamed in X+2
            - migration 'state' should be 'available'
        """
        # Create the next module
        next_module = self.module.copy({"name": "next_module"})
        next_module_branch = self._create_odoo_module_branch(
            next_module,
            self.next_branch,
            specific=False,
            repository_branch_id=self.repo_branch2.id,
            last_scanned_commit="sha_next",
        )
        # Create the target module
        # /!\ We do not create the target module branch on X+2 on purpose,
        # so the project migration record cannot find a matching module.
        target_module = self.module.copy({"name": "target_module"})
        # Generate project_migration data records from X to X+2 (with a gap)
        self._generate_migration_data(self.project, self.migration_path)
        # Module has been renamed in X+1
        self._create_timeline(self.module_branch, next_module, "renamed")
        renamed_to_module = self.module_branch._renamed_to_module_in_target_version(
            self.next_branch
        )
        self.assertEqual(renamed_to_module, next_module)
        # Module has been renamed again in X+2
        self._create_timeline(next_module_branch, target_module, "renamed")
        renamed_to_module = self.module_branch._renamed_to_module_in_target_version(
            self.target_branch
        )
        self.assertEqual(renamed_to_module, target_module)
        # Check migration data
        mig = self.project.module_migration_ids
        self.assertEqual(mig.renamed_to_module_id, target_module)
        self.assertFalse(mig.replaced_by_module_id)
        self.assertFalse(mig.target_module_branch_id)
        self.assertEqual(mig.state, "migrate")
        # Now we create the target module branch on X+2, the project migration
        # data should consider it
        target_module_branch = self._create_odoo_module_branch(
            target_module,
            self.target_branch,
            specific=False,
            repository_branch_id=self.repo_branch3.id,
            last_scanned_commit="sha_target",
        )
        self.assertEqual(mig.target_module_branch_id, target_module_branch)
        self.assertEqual(mig.state, "available")
