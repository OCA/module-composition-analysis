# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class OdooModuleBranch(models.Model):
    _inherit = "odoo.module.branch"

    migration_ids = fields.One2many(
        comodel_name="odoo.module.branch.migration",
        inverse_name="module_branch_id",
        string="Migrations",
    )

    migration_scan = fields.Boolean(
        compute="_compute_migration_scan",
        store=True,
        help="Technical field telling if this module is elligible for a migration scan.",
    )

    @api.depends(
        "last_scanned_commit",
        "migration_ids.last_source_scanned_commit",
    )
    def _compute_migration_scan(self):
        for rec in self:
            # Default repository migration scan policy
            rec.migration_scan = rec.repository_id.collect_migration_data
            if not rec.migration_scan:
                continue
            # Repository scan has to be performed first
            if not rec.last_scanned_commit:
                continue
            # Migration scan to do as soon as a migration path is missing
            # among existing scans
            available_migration_paths = self.env["odoo.migration.path"].search(
                [("source_branch_id", "=", rec.branch_id.id)]
            )
            scanned_migration_paths = rec.migration_ids.migration_path_id.filtered(
                "active"
            )
            if available_migration_paths != scanned_migration_paths:
                rec.migration_scan = True
                continue
            # Migration scan to do if last scanned commit doesn't match the last
            # migration scan
            for migration in rec.migration_ids:
                if migration.last_source_scanned_commit != rec.last_scanned_commit:
                    rec.migration_scan = True
                    break
            # Reaching this point means no scan is required
            rec.migration_scan = False

    def _to_dict(self):
        # Add the migrations data
        data = super()._to_dict()
        data["migrations"] = []
        for migration in self.migration_ids:
            data["migrations"].append(migration._to_dict())
        return data
