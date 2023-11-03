# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class OdooModuleBranch(models.Model):
    _inherit = "odoo.module.branch"

    odoo_project_module_ids = fields.One2many(
        comodel_name="odoo.project.module",
        inverse_name="module_branch_id",
        string="Deployed Modules",
    )
    odoo_project_ids = fields.Many2many(
        comodel_name="odoo.project",
        relation="odoo_project_module_branch_rel",
        column1="module_branch_id", column2="odoo_project_id",
        string="Projects",
        compute="_compute_module_ids",
        store=True,
    )

    @api.depends("odoo_project_module_ids.odoo_project_id")
    def _compute_module_ids(self):
        for rec in self:
            rec.odoo_project_ids = rec.odoo_project_module_ids.odoo_project_id.ids
