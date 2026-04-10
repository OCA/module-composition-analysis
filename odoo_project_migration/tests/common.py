# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.tests import Form

from odoo.addons.odoo_project.tests.common import ProjectCommon
from odoo.addons.odoo_repository_migration.tests.common import MigrationCommon


class ProjectMigrationCommon(ProjectCommon, MigrationCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mig_path_model = cls.env["odoo.migration.path"]
        cls.wiz_generate_mig_data_model = cls.env[
            "odoo.project.generate.migration.data"
        ]
        cls.wiz_export_mig_report_model = cls.env[
            "odoo.project.export.migration.report"
        ]

    @classmethod
    def _generate_migration_data(cls, project, migration_path):
        wiz_model = cls.wiz_generate_mig_data_model.with_context(
            default_odoo_project_id=project.id
        )
        with Form(wiz_model) as form:
            form.migration_path_id = migration_path
            wiz = form.save()
        wiz.action_generate_data()
        cls.env.flush_all()  # Force fields computation
        return wiz

    @classmethod
    def _export_migration_report(cls, project, migration_path):
        wiz_model = cls.wiz_export_mig_report_model.with_context(
            default_odoo_project_id=project.id
        )
        with Form(wiz_model) as form:
            form.migration_path_id = migration_path
            wiz = form.save()
        return wiz.action_export_report()
