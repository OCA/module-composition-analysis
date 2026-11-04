# Copyright 2026 Sebastien Alix <https://github.com/sebalix>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class OdooModuleBranchData(models.Model):
    _name = "odoo.module.branch.data"
    _description = "Odoo Data"
    _order = "odoo_model_name, name"

    module_branch_id = fields.Many2one(
        comodel_name="odoo.module.branch",
        ondelete="cascade",
        string="Module",
        index=True,
    )
    module_id = fields.Many2one(
        string="Module technical name",
        related="module_branch_id.module_id",
        store=True,
        index=True,
    )
    module_name = fields.Char(
        string="Module technical name ",
        related="module_branch_id.module_name",
        store=True,
        index="trigram",
    )
    odoo_model_version_id = fields.Many2one(
        comodel_name="odoo.model.version",
        ondelete="restrict",
        string="Model (for this Odoo version)",
        required=True,
        index=True,
    )
    odoo_model_id = fields.Many2one(
        related="odoo_model_version_id.odoo_model_id",
        string="Model",
        store=True,
        index=True,
    )
    odoo_model_name = fields.Char(
        related="odoo_model_version_id.odoo_model_id.name",
        string="Model name",
        store=True,
        index=True,
    )
    odoo_version_id = fields.Many2one(
        related="module_branch_id.branch_id", store=True, index=True
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
        compute="_compute_display_name", store=True, index="trigram"
    )
    name = fields.Char(required=True, index=True)
    xml_id = fields.Char(string="External ID", required=True, index="trigram")
    file_path = fields.Char(string="File", index=True)
    data_type = fields.Selection(
        selection=[
            ("data", "Data"),
            ("demo", "Demo"),
        ],
        string="Type",
        required=True,
        default="data",
        index=True,
    )
    loaded = fields.Boolean(
        help="True if the data is loaded by the module "
        "(declared in the 'data' or 'demo' keys of its manifest).",
    )
    noupdate = fields.Boolean()
    data = fields.Serialized()
    active = fields.Boolean(default=True)

    @api.depends("odoo_model_name", "xml_id", "module_branch_id")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = (
                f"<{rec.odoo_model_name}>.{rec.xml_id} "
                f"in {rec.module_branch_id.display_name}"
            )

    def _to_dict(self):
        self.ensure_one()
        return dict(self.data)
