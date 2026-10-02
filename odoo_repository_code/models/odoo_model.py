# Copyright 2025 Sebastien Alix <https://github.com/sebalix>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class OdooModel(models.Model):
    _name = "odoo.model"
    _description = "Odoo Model Technical Name"

    name = fields.Char(required=True, index=True)
