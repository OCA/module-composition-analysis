# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class MyModel(models.Model):
    _name = "my_module.my_model"
    _description = "My Model"

    name = fields.Char()

    def my_method(self):
        return True
