# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class AuthenticationToken(models.Model):
    _name = "authentication.token"
    _description = "Authentication Token"

    name = fields.Char(required=True)
    token = fields.Char(required=True)
