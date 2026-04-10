# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from .common import ProjectMigrationCommon


class TestOdooProjectGenerateMigrationData(ProjectMigrationCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.migration_path = cls.mig_path_model.create(
            {
                "source_branch_id": cls.branch.id,
                "target_branch_id": cls.branch2.id,
            }
        )
        # Retrieve migration data for `cls.module_branch`
        cls._simulate_migration_scan(
            "target_commit1", report={"process": "migrate", "results": {}}
        )
        # And import/install this module in our project
        cls._run_import_modules(cls.project, cls.module_branch.module_name)

    def test_generate_migration_data(self):
        self.assertFalse(self.project.module_migration_ids)
        self._generate_migration_data(self.project, self.migration_path)
        # Check project module migration records
        module_migs = self.project.module_migration_ids
        self.assertTrue(module_migs)
        self.assertRecordValues(
            module_migs,
            [
                {
                    "migration_path_id": self.migration_path.id,
                    "source_module_branch_id": self.module_branch.id,
                    "target_module_branch_id": False,
                    "project_module_id": self.project.project_module_ids.id,
                    "module_migration_id": self.module_branch.migration_ids.id,
                    "state": "migrate",
                }
            ],
        )

    def test_generate_migration_data_existing_data_removed(self):
        self.assertFalse(self.project.module_migration_ids)
        self._generate_migration_data(self.project, self.migration_path)
        # Check project module migration records
        module_migs = self.project.module_migration_ids
        self.assertTrue(module_migs)
        # Re-generate migration data => new records are created
        self._generate_migration_data(self.project, self.migration_path)
        new_module_migs = self.project.module_migration_ids
        self.assertTrue(new_module_migs.exists())
        self.assertFalse(module_migs.exists())
