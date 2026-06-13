# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import csv
import io

from .common import ProjectMigrationCommon


class TestOdooProjectExportMigrationReport(ProjectMigrationCommon):
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
            "target_commit1",
            source=cls.branch,
            target=cls.branch2,
            report={"process": "migrate", "results": {}},
        )
        # And import/install this module in our project
        cls._run_import_modules(cls.project, cls.module_branch.module_name)
        # Generate migration data
        cls._generate_migration_data(cls.project, cls.migration_path)

    def test_export_migration_report(self):
        """Test the export migration report wizard."""
        action = self._export_migration_report(self.project, self.migration_path)
        # Check action export report
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn("web/content/?model=ir.attachment", action["url"])
        # Check attachment created
        attachment = self.env["ir.attachment"].search(
            [("res_model", "=", self.project._name), ("res_id", "=", self.project.id)]
        )
        self.assertTrue(attachment)
        self.assertIn(".csv", attachment.name)
        self.assertEqual(attachment.type, "binary")

    def test_export_migration_report_csv_content(self):
        """Test the CSV content of the export migration report."""
        project_mod = self.project.project_module_ids
        # Get CSV content
        wiz = self.wiz_export_mig_report_model.with_context(
            default_odoo_project_id=self.project.id
        ).create(
            {
                "migration_path_id": self.migration_path.id,
            }
        )
        content = wiz._get_csv_content()
        file_ = io.StringIO(content)
        reader = csv.DictReader(file_)
        rows = list(reader)
        repo_row, module_row = rows
        # Repository row
        self.assertEqual(repo_row["Repository"], project_mod.repository_id.display_name)
        self.assertFalse(repo_row["Module"])
        # Module row
        self.assertDictEqual(
            module_row,
            {
                "Repository": "",
                "Module": project_mod.module_name,
                "Dependencies": "",
                "Global Dep. Level": "1",
                "Non-Std Dep. Level": "1",
                "Info": "",
                "Warning": "",
                "Python": "0",
                "JavaScript": "0",
                "CSS": "0",
                "XML": "0",
                "Status": "migrate",
            },
        )
