# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooModuleBranch(models.Model):
    _inherit = "odoo.module.branch"

    migration_ids = fields.One2many(
        comodel_name="odoo.module.branch.migration",
        inverse_name="module_branch_id",
        string="Migrations",
    )

    def _to_dict(self):
        # Add the migrations data
        data = super()._to_dict()
        data["migrations"] = []
        for migration in self.migration_ids:
            data["migrations"].append(migration._to_dict())
        return data
