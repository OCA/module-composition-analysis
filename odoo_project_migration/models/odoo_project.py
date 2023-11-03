# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import ast

from odoo import _, api, fields, models


class OdooProject(models.Model):
    _inherit = "odoo.project"

    module_migration_ids = fields.One2many(
        comodel_name="odoo.project.module.migration",
        inverse_name="odoo_project_id",
        string="Migration Data",
    )
    migrations_count = fields.Integer(compute="_compute_migrations_count")

    @api.depends("module_migration_ids")
    def _compute_migrations_count(self):
        for rec in self:
            rec.migrations_count = len(rec.module_migration_ids)

    def open_generate_migration_data(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "odoo_project_migration.odoo_project_generate_migration_data_action"
        )
        ctx = action.get("context", {})
        if isinstance(ctx, str):
            ctx = ast.literal_eval(ctx)
        ctx["default_odoo_project_id"] = self.id
        action["context"] = ctx
        return action

    def open_create_migration_report(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "odoo_project_migration.odoo_project_create_migration_report_action"
        )
        ctx = action.get("context", {})
        if isinstance(ctx, str):
            ctx = ast.literal_eval(ctx)
        ctx["default_odoo_project_id"] = self.id
        action["context"] = ctx
        return action

    def open_migration_data(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "odoo_project_migration.odoo_project_module_migration_action"
        )
        ctx = action.get("context", {})
        if isinstance(ctx, str):
            ctx = ast.literal_eval(ctx)
        action["domain"] = [("odoo_project_id", "=", self.id)]
        migration_paths = self.module_migration_ids.migration_path_id
        if len(migration_paths) == 1:
            action["display_name"] = _("Migration") + f" {migration_paths.name}"
        else:
            ctx["search_default_group_by_migration_path_id"] = 1
        ctx["search_default_group_by_org_id"] = 2
        ctx["search_default_group_by_state"] = 3
        action["context"] = ctx
        return action
