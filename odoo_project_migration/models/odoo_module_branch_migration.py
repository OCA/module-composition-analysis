# Copyright 2025 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooModuleBranchMigration(models.Model):
    _inherit = "odoo.module.branch.migration"

    odoo_project_ids = fields.Many2many(related="module_branch_id.odoo_project_ids")
