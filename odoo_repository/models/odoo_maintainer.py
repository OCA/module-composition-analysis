# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models

from ..utils.github import GITHUB_URL


class OdooMaintainer(models.Model):
    _name = "odoo.maintainer"
    _description = "Odoo Module Maintainer"
    _order = "name"

    name = fields.Char(required=True, index=True)
    github_url = fields.Char(string="GitHub URL", compute="_compute_github_url")
    module_branch_ids = fields.Many2many(
        comodel_name="odoo.module.branch",
        relation="module_branch_maintainer_rel",
        column1="maintainer_id", column2="module_branch_id",
        string="Maintainers",
    )

    @api.depends("name")
    def _compute_github_url(self):
        for rec in self:
            rec.github_url = f"{GITHUB_URL}/{rec.name}"

    _sql_constraints = [
        (
            "name_uniq",
            "UNIQUE (name)",
            "This maintainer already exists."
        ),
    ]
