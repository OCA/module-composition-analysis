# Copyright 2025 Sebastien Alix <https://github.com/sebalix>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models


class OdooRepository(models.Model):
    _inherit = "odoo.repository"

    def _prepare_scanner_parameters(self, version, branch):
        params = super()._prepare_scanner_parameters(version, branch)
        params["parse_code"] = True
        return params
