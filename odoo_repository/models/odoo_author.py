# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooAuthor(models.Model):
    _name = "odoo.author"
    _description = "Odoo Module Author"
    _order = "name"

    name = fields.Char(required=True, index=True)

    _sql_constraints = [
        ("name_uniq", "UNIQUE (name)", "This author already exists."),
    ]
