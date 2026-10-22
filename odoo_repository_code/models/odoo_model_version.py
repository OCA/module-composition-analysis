# Copyright 2025 Sebastien Alix <https://github.com/sebalix>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class OdooModelVersion(models.Model):
    _name = "odoo.model.version"
    _description = "Odoo Model Technical Name for Odoo Version"

    odoo_model_id = fields.Many2one(
        comodel_name="odoo.model",
        ondelete="cascade",
        string="Odoo Model",
        required=True,
        index=True,
    )
    odoo_version_id = fields.Many2one(
        comodel_name="odoo.branch",
        ondelete="restrict",
        string="Odoo Version",
        required=True,
        index=True,
    )
    name = fields.Char(compute="_compute_name", store=True)
    module_branch_model_ids = fields.One2many(
        comodel_name="odoo.module.branch.model",
        inverse_name="odoo_model_version_id",
        string="Models",
    )

    @api.depends("odoo_model_id", "odoo_version_id")
    def _compute_name(self):
        for rec in self:
            rec.name = f"[{rec.odoo_version_id.name}] {rec.odoo_model_id.name}"
