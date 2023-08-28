# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooModule(models.Model):
    _name = "odoo.module"
    _description = "Odoo Module Technical Name"

    name = fields.Char(required=True, index=True, help="Technical Name")
    module_branch_ids = fields.One2many(
        comodel_name="odoo.module.branch",
        inverse_name="module_id",
        string="Modules",
    )

    _sql_constraints = [
        (
            "name_uniq",
            "UNIQUE (name)",
            "This module technical name already exists."
        ),
    ]
