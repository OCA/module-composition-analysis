# Copyright 2025 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models


class OdooProjectModule(models.Model):
    _inherit = "odoo.project.module"

    def open_next_module_branches(self):
        self.ensure_one()
        return self.module_branch_id.open_next_module_branches()
