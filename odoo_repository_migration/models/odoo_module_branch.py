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
        "removed",
        "pr_url",
        "last_scanned_commit",
        "migration_ids.migration_scan",
        "repository_id.collect_migration_data",
    )
    def _compute_migration_scan(self):
        for rec in self:
            # Do not scan removed or pending (in PR) modules
            if rec.removed or rec.pr_url:
                rec.migration_scan = False
                continue
            # Default repository migration scan policy
            rec.migration_scan = rec.repository_id.collect_migration_data
            if not rec.migration_scan:
                continue
            # Repository scan has to be performed first
            if not rec.last_scanned_commit:
                continue
            # Migration scan to do as soon as a migration path is missing
            # among existing scans. However, we remove migration path that doesn't
            # match branches scanned in the repository (e.g. 18.0 branch could
            # be missing in a repo while a migration path 16.0 -> 18.0 is
            # configured, so no need to do a migration scan in this case).
            available_repo_branches = rec.repository_id.branch_ids.branch_id
            available_migration_paths = self.env["odoo.migration.path"].search(
                [
                    ("source_branch_id", "=", rec.branch_id.id),
                    ("target_branch_id", "in", available_repo_branches.ids),
                ]
            )
            scanned_migration_paths = rec.migration_ids.migration_path_id
            if available_migration_paths != scanned_migration_paths:
                rec.migration_scan = True
                continue
            # Migration scan to do if any of the migration path requires one
            rec.migration_scan = any(rec.migration_ids.mapped("migration_scan"))

    def _to_dict(self):
        # Add the migrations data
        data = super()._to_dict()
        data["migrations"] = []
        for migration in self.migration_ids:
            data["migrations"].append(migration._to_dict())
        return data

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs._update_migration_target_module_id()
        return recs

    def write(self, vals):
        res = super().write(vals)
        # When 'pr_url' is set or unset, this means the module has been found
        # in a PR or has been merged upstream. We want to recompute the target
        # module in migration data in such case.
        if "pr_url" in vals:
            self._update_migration_target_module_id()
        return res

    def _update_migration_target_module_id(self):
        """Update `target_module_id` field on relevant module migration records."""
        for rec in self:
            migrations = self.env["odoo.module.branch.migration"].search(
                [
                    ("module_id", "=", rec.module_id.id),
                    ("target_branch_id", "=", rec.branch_id.id),
                ]
            )
            # Recompute 'target_module_id' field
            migrations._compute_target_module_branch_id()
