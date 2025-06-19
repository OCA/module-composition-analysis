# Copyright 2025 Raphaël Reverdy <raphael.reverdy@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models


class OdooProjectGenerateMigrationData(models.TransientModel):
    _inherit = "odoo.project.generate.migration.data"

    def _modules_to_migrate(self):
        return self.odoo_project_id._modules_to_migrate(self.migration_path_id)
