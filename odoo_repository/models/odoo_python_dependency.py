# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooPythonDependency(models.Model):
    _name = "odoo.python.dependency"
    _description = "Odoo Python Dependency"
    _order = "name"

    name = fields.Char(required=True, index=True)

    _sql_constraints = [
        ("name_uniq", "UNIQUE (name)", "This Python dependency already exists."),
    ]
