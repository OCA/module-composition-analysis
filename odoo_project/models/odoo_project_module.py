# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models
from odoo.tools.parse_version import parse_version as v


class OdooProjectModule(models.Model):
    _name = "odoo.project.module"
    _inherits = {"odoo.module.branch": "module_branch_id"}
    _description = "Odoo Project Module"
    _order = "name"

    odoo_project_id = fields.Many2one(
        comodel_name="odoo.project",
        ondelete="cascade",
        string="Project",
    )
    module_branch_id = fields.Many2one(
        comodel_name="odoo.module.branch",
        ondelete="set null",
        string="Upstream Module",
        required=True,
    )
    installed_version = fields.Char()
    to_upgrade = fields.Boolean(
        string="To Upgrade",
        compute="_compute_to_upgrade",
        store=True,
    )

    @api.depends("version", "installed_version")
    def _compute_to_upgrade(self):
        for rec in self:
            rec.to_upgrade = False
            installed_version = rec.installed_version or rec.version
            if installed_version and rec.version:
                rec.to_upgrade = v(installed_version) < v(rec.version)
