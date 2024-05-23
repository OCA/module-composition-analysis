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
            "This migration path already exists.",
        ),
    ]

    @api.depends("source_branch_id.name", "target_branch_id.name")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.source_branch_id.name} -> {rec.target_branch_id.name}"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Automatically launch a scan on all relevant repositories when a
        # migration path is created
        if not self.env.context.get("disable_force_scan"):
            records.action_force_scan()
        return records

    def action_force_scan(self):
        """Force the scan of the source branch.

        Scan is done on all related repositories configured to collect migration data.
        """
        branches = self.source_branch_id | self.target_branch_id
        return branches.repository_branch_ids.filtered(
            lambda o: o.repository_id.collect_migration_data
        ).action_force_scan()
