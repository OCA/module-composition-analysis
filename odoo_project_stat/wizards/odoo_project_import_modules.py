# Copyright 2025 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models


class OdooProjectImportModules(models.TransientModel):
    _inherit = "odoo.project.import.modules"

    def action_import(self):
        res = super().action_import()
        # Generate project stats each time we import new modules
        self.odoo_project_id.action_generate_stats()
        return res
