# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooModuleDevStatus(models.Model):
    _name = "odoo.module.dev.status"
    _description = "Odoo Module Development Status"

    name = fields.Char(required=True, index=True)

    _sql_constraints = [
        ("name_uniq", "UNIQUE (name)", "This development_status already exists."),
    ]
