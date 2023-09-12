# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooProjectCreateMigrationReport(models.TransientModel):
    _name = "odoo.project.create.migration.report"
    _description = "Create a migration report for an Odoo project"

    odoo_project_id = fields.Many2one(
        comodel_name="odoo.project",
        string="Project",
        required=True,
    )
    odoo_version_id = fields.Many2one(related="odoo_project_id.odoo_version_id")
    migration_path_id = fields.Many2one(
        comodel_name="odoo.migration.path",
        string="Migration Path",
        required=True,
    )

    def action_create_report(self):
        """Create a migration report for the given Odoo project."""
        self.ensure_one()
        module_migration_model = self.env["odoo.project.module.migration"]
        module_migrations_to_unlink = module_migration_model.search(
            [
                ("odoo_project_id", "=", self.odoo_project_id.id),
                ("migration_path_id", "=", self.migration_path_id.id),
            ]
        )
        module_migrations_to_unlink.sudo().unlink()
        values_list = []
        for module_branch in self.odoo_project_id.module_branch_ids:
            values = self._prepare_module_migration_values(module_branch)
            values_list.append(values)
        module_migration_model.sudo().create(values_list)
        return True

    def _prepare_module_migration_values(self, module_branch):
        return {
            "odoo_project_id": self.odoo_project_id.id,
            "migration_path_id": self.migration_path_id.id,
            "source_module_branch_id": module_branch.id,
        }
