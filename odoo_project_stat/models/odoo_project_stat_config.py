# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooProjectStatConfig(models.Model):
    _name = "odoo.project.stat.config"
    _description = "Odoo Project Stat Config"
    _order = "sequence, name"

    sequence = fields.Integer(default=10)
    name = fields.Char(string="Title", required=True)
    color = fields.Char(required=True)
    residual = fields.Boolean(
        help=(
            "Will catch all modules that doesn't match other rules "
            "(domain field will be ignored if enabled)."
        )
    )
    domain = fields.Char()

    _sql_constraints = [
        (
            "residual_uniq",
            "UNIQUE (residual)",
            "Only one configuration should exist for residual modules.",
        ),
    ]
