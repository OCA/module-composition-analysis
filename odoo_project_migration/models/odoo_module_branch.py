# Copyright 2026  Akretion (https://www.akretion.com).
# @author Sébastien Alix <sebastien.alix@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models


class OdooModuleBranch(models.Model):
    _inherit = "odoo.module.branch"

    def _update_migration_data(self):
        # Override to refresh project migration data as well
        res = super()._update_migration_data()
        for rec in self:
            timelines = rec._get_related_timelines()
            impacted_modules = rec.module_id | timelines._get_all_impacted_modules()
            migrations = self.env["odoo.project.module.migration"].search(
                [
                    ("module_id", "in", impacted_modules.ids),
                    (
                        "migration_path_id.source_branch_id.sequence",
                        "<=",
                        rec.branch_id.sequence,
                    ),
                    (
                        "migration_path_id.target_branch_id.sequence",
                        ">=",
                        rec.branch_id.sequence,
                    ),
                ]
            )
            migrations.force_update()
        return res
