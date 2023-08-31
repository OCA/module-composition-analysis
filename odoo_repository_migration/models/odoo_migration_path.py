# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class OdooMigrationPath(models.Model):
    _name = "odoo.migration.path"
    _description = "Define a migration path (from one branch to another)"
    _order = "name"

    name = fields.Char(compute="_compute_name", store=True)
    active = fields.Boolean(default=True)
    source_branch_id = fields.Many2one(
        comodel_name="odoo.branch",
        ondelete="cascade",
        domain=[("odoo_version", "=", True)],
        required=True,
    )
    target_branch_id = fields.Many2one(
        comodel_name="odoo.branch",
        ondelete="cascade",
        domain=[("odoo_version", "=", True)],
        required=True,
    )

    _sql_constraints = [
        (
            "migration_path_uniq",
            "UNIQUE (source_branch_id, target_branch_id)",
            "This migration path already exists."
        ),
    ]

    @api.depends("source_branch_id.name", "target_branch_id.name")
    def _compute_name(self):
        for rec in self:
            rec.name = (
                f"{rec.source_branch_id.name} -> {rec.target_branch_id.name}"
            )
