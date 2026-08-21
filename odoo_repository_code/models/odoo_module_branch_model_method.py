# Copyright 2025 Sebastien Alix <https://github.com/sebalix>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models


class OdooModuleBranchModelMethod(models.Model):
    _name = "odoo.module.branch.model.method"
    _inherit = "odoo.module.branch.model.resource.mixin"
    _description = "Odoo method"
    _order = "odoo_model_name, name"

    data = fields.Serialized()
    signature = fields.Char(compute="_compute_signature", store=True)
    code = fields.Text(compute="_compute_code", store=True)
    global_dependency_level = fields.Integer(
        related="module_branch_model_id.module_branch_id.global_dependency_level",
        store=True,
    )
    root_id = fields.Many2one(
        string="Origin",
        comodel_name="odoo.module.branch.model.method",
        compute="_compute_root_id",
    )
    parent_ids = fields.One2many(
        comodel_name="odoo.module.branch.model.method",
        compute="_compute_parent_ids",
        string="Parent Methods",
    )

    @api.depends("data")
    def _compute_signature(self):
        for rec in self:
            signature = ", ".join(rec.data.get("signature", []))
            rec.signature = f"{rec.name}({signature})"

    @api.depends("data")
    def _compute_code(self):
        for rec in self:
            decorators = "\n    @".join(rec.data.get("decorators", [])).strip()
            if decorators:
                decorators = f"    @{decorators}\n"
            code = rec.data.get("code", "")
            rec.code = f"{decorators}{code}"

    @api.depends("module_branch_model_id.module_branch_id", "odoo_version_id", "name")
    def _compute_root_id(self):
        for rec in self:
            parent_methods = rec._get_parent_methods()
            root = fields.first(parent_methods)
            rec.root_id = root if root != rec else False

    @api.depends("module_branch_model_id", "name")
    def _compute_parent_ids(self):
        for rec in self:
            rec.parent_ids = rec._get_parent_methods()

    def _get_parent_methods(self, order="global_dependency_level"):
        """Return all parent methods from dependencies (call stack)."""
        self.ensure_one()
        # Get all parent models
        parent_models = self.module_branch_model_id._get_parent_models()
        # Find methods with the same name in parent models
        parent_methods = self.search(
            [
                ("module_branch_model_id", "in", parent_models.ids),
                ("name", "=", self.name),
            ],
            order=order,
        )
        return parent_methods

    def open_parent_methods(self):
        self.ensure_one()
        xml_id = "odoo_repository_code.odoo_module_branch_model_method_action2"
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        action["name"] = _("Parent Methods")
        action["domain"] = [("id", "in", self.parent_ids.ids)]
        action["context"] = {}
        return action

    def _to_dict(self, code=False):
        self.ensure_one()
        data = {
            "name": self.name,
            "signature": self.signature,
        }
        if code:
            data["code"] = self.code
        return data
