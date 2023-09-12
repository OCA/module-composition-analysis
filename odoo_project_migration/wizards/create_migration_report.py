# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class OdooProjectCreateMigrationReport(models.TransientModel):
    _name = "odoo.project.create.migration.report"
    _description = "Create a migration report for an Odoo project"

    odoo_project_id = fields.Many2one(
        comodel_name="odoo.project",
        string="Project",
        required=True,
    )
    odoo_version_id = fields.Many2one(related="odoo_project_id.odoo_version_id")
    available_migration_path_ids = fields.One2many(
        comodel_name="odoo.migration.path",
        compute="_compute_available_migration_path_ids",
        string="Available Migration Paths",
    )
    migration_path_id = fields.Many2one(
        comodel_name="odoo.migration.path",
        string="Migration Path",
        required=True,
    )

    @api.depends("odoo_project_id")
    def _compute_available_migration_path_ids(self):
        for rec in self:
            rec.available_migration_path_ids = (
                rec.odoo_project_id.module_migration_ids.migration_path_id
            )

    def action_create_report(self):
        """Create a migration report for the given Odoo project."""
        self.ensure_one()
        # TODO
        return True
