# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooModuleBranch(models.Model):
    _inherit = "odoo.module.branch"

    odoo_project_ids = fields.Many2many(
        comodel_name="odoo.project",
        relation="odoo_project_module_branch_rel",
        column1="module_branch_id", column2="odoo_project_id",
        string="Projects",
    )
