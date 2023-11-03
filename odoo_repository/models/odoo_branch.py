# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooBranch(models.Model):
    _name = "odoo.branch"
    _description = "Odoo Branch"
    _order = "name"

    name = fields.Char(required=True, index=True)
    odoo_version = fields.Boolean(default=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "UNIQUE (name)", "This branch already exists."),
    ]
