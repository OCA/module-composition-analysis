# Copyright 2025 Camptocamp SA
# Copyright 2026  Akretion (https://www.akretion.com).
# @author Sébastien Alix <sebastien.alix@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, fields, models


class OdooModuleBranchMigration(models.Model):
    _inherit = "odoo.module.branch.migration"

    odoo_project_ids = fields.Many2many(related="module_branch_id.odoo_project_ids")
    odoo_project_module_migration_ids = fields.One2many(
        comodel_name="odoo.project.module.migration",
        inverse_name="module_migration_id",
        string="Project Migrations",
    )

    def open_project_migrations(self):
        self.ensure_one()
        xml_id = "odoo_project_migration.odoo_project_module_migration_action"
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        action["name"] = _("Project migrations")
        action["domain"] = [("id", "in", self.odoo_project_module_migration_ids.ids)]
        return action
