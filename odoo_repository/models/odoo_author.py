# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooAuthor(models.Model):
    _name = "odoo.author"
    _description = "Odoo Module Author"
    _order = "name"

    name = fields.Char(required=True, index=True)

    _name_uniq = models.Constraint(
        "UNIQUE (name)",
        "This author already exists.",
    )
