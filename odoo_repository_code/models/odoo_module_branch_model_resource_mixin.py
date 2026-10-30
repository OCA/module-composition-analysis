# Copyright 2025 Sebastien Alix <https://github.com/sebalix>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class OdooModuleBranchModelResourceMixin(models.AbstractModel):
    _name = "odoo.module.branch.model.resource.mixin"
    _description = "Odoo Model Resource Mixin"
    _order = "odoo_model_name, name"

    module_branch_model_id = fields.Many2one(
        comodel_name="odoo.module.branch.model",
        ondelete="cascade",
        string="Model",
        required=True,
        index=True,
    )
    module_branch_id = fields.Many2one(
        related="module_branch_model_id.module_branch_id",
        store=True,
        index=True,
    )
    module_name = fields.Char(
        related="module_branch_model_id.module_name",
        string="Technical module name",
        required=True,
        store=True,
        precompute=True,
        index=True,
    )
    odoo_model_id = fields.Many2one(
        related="module_branch_model_id.odoo_model_id",
        string="Model ",
        required=True,
        store=True,
        precompute=True,
        index=True,
    )
    odoo_model_name = fields.Char(
        related="module_branch_model_id.odoo_model_name",
        string="Model name",
        required=True,
        store=True,
        precompute=True,
        index=True,
    )
    odoo_version_id = fields.Many2one(
        related="module_branch_model_id.odoo_version_id",
        string="Odoo Version",
        required=True,
        store=True,
        precompute=True,
        index=True,
    )
    org_id = fields.Many2one(related="module_branch_id.org_id", store=True, index=True)
    repository_id = fields.Many2one(
        related="module_branch_id.repository_id", store=True, index=True
    )
    global_dependency_level = fields.Integer(
        string="Dep. Level",
        related="module_branch_id.global_dependency_level",
        store=True,
    )
    display_name = fields.Char(
        compute="_compute_display_name",
        store=True,
        index="trigram",
    )
    name = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)

    @api.depends("module_name", "odoo_model_name", "name")
    def _compute_display_name(self):
        for rec in self:
            model_name = rec.odoo_model_name
            rec.display_name = (
                f"<{model_name}>.{rec.name} in {rec.module_branch_id.display_name}"
            )
