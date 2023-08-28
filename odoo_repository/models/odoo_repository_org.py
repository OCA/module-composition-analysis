# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models

from ..utils.github import GITHUB_URL


class OdooRepositoryOrg(models.Model):
    _name = "odoo.repository.org"
    _description = "Odoo Repository Organization"

    name = fields.Char(required=True, index=True)
    github_url = fields.Char(string="GitHub URL", compute="_compute_github_url")

    @api.depends("name")
    def _compute_github_url(self):
        for rec in self:
            rec.github_url = f"{GITHUB_URL}/{rec.name}"

    _sql_constraints = [
        (
            "name_uniq",
            "UNIQUE (name)",
            "This organization already exists."
        ),
    ]
