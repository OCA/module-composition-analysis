# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooModuleCategory(models.Model):
    _name = "odoo.module.category"
    _description = "Odoo Module Category"

    name = fields.Char(required=True, index=True)

    _sql_constraints = [
        (
            "name_uniq",
            "UNIQUE (name)",
            "This module category already exists."
        ),
    ]
