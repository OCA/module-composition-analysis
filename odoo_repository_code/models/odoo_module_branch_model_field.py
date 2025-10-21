# Copyright 2025 Sebastien Alix <https://github.com/sebalix>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models


class OdooModuleBranchModelField(models.Model):
    _name = "odoo.module.branch.model.field"
    _inherit = "odoo.module.branch.model.resource.mixin"
    _description = "Odoo field"

    field_type = fields.Char(string="Type", required=True, index=True)
    data = fields.Serialized()
    code = fields.Text(compute="_compute_code", store=True, index="trigram")
    comodel_name = fields.Char(compute="_compute_comodel_name", store=True, index=True)
    comodel_id = fields.Many2one(
        comodel_name="odoo.model.version",
        compute="_compute_comodel_id",
    )
    is_relational = fields.Boolean(compute="_compute_is_relational", store=True)
    inverse_method = fields.Char(
        string="Inverse method name",
        compute="_compute_methods",
        store=True,
    )
    inverse_method_id = fields.Many2one(
        comodel_name="odoo.module.branch.model.method",
        compute="_compute_methods_id",
    )
    search_method = fields.Char(
        string="Search method name",
        compute="_compute_methods",
        store=True,
    )
    search_method_id = fields.Many2one(
        comodel_name="odoo.module.branch.model.method",
        compute="_compute_methods_id",
    )
    root_id = fields.Many2one(
        string="Origin",
        comodel_name="odoo.module.branch.model.field",
        compute="_compute_root_id",
    )
    parent_ids = fields.One2many(
        comodel_name="odoo.module.branch.model.field",
        compute="_compute_parent_ids",
        string="Parent Fields",
    )

    @api.depends("data")
    def _compute_code(self):
        for rec in self:
            rec.code = rec.data.get("code", False)

    @api.depends("data")
    def _compute_comodel_name(self):
        for rec in self:
            rec.comodel_name = rec.data.get("comodel_name")

    @api.depends("comodel_name", "odoo_model_id", "odoo_version_id")
    def _compute_comodel_id(self):
        model_model = self.env["odoo.model.version"]
        for rec in self:
            rec.comodel_id = False
            if rec.comodel_name:
                model = model_model.search(
                    [
                        ("odoo_model_id.name", "=", rec.comodel_name),
                        ("odoo_version_id", "=", rec.odoo_version_id.id),
                    ]
                )
                rec.comodel_id = model

    @api.depends("field_type")
    def _compute_is_relational(self):
        for rec in self:
            rec.is_relational = (
                rec.field_type.startswith("One2")
                or rec.field_type.startswith("Many2")
                or rec.field_type == "Reference"
            )

    @api.depends("data")
    def _compute_methods(self):
        for rec in self:
            kwargs = rec.data.get("kwargs", {})
            rec.inverse_method = kwargs.get("inverse")
            rec.search_method = kwargs.get("search")

    @api.depends("inverse_method", "search_method")
    def _compute_methods_id(self):
        method_model = self.env["odoo.module.branch.model.method"]
        for rec in self:
            rec.inverse_method_id = rec.search_method_id = False
            # Inverse method
            if rec.inverse_method:
                method = method_model.search(
                    [
                        ("module_branch_model_id", "=", rec.module_branch_model_id.id),
                        ("name", "=", rec.inverse_method),
                    ],
                    limit=1,
                )
                rec.inverse_method_id = method
            # Search method
            if rec.search_method:
                method = method_model.search(
                    [
                        ("module_branch_model_id", "=", rec.module_branch_model_id.id),
                        ("name", "=", rec.search_method),
                    ],
                    limit=1,
                )
                rec.search_method_id = method

    @api.depends("module_branch_model_id.module_branch_id", "odoo_version_id", "name")
    def _compute_root_id(self):
        for rec in self:
            parent_fields = rec._get_parent_fields()
            root = fields.first(parent_fields)
            rec.root_id = root if root != rec else False

    @api.depends("module_branch_model_id", "name")
    def _compute_parent_ids(self):
        for rec in self:
            rec.parent_ids = rec._get_parent_fields()

    def _get_parent_fields(self, order="global_dependency_level"):
        """Return all parent fields from dependencies (call stack)."""
        self.ensure_one()
        # Get all parent models
        parent_models = self.module_branch_model_id._get_parent_models()
        # Find fields with the same name in parent models
        parent_fields = self.search(
            [
                ("module_branch_model_id", "in", parent_models.ids),
                ("name", "=", self.name),
            ],
            order=order,
        )
        return parent_fields

    def open_parent_fields(self):
        self.ensure_one()
        xml_id = "odoo_repository_code.odoo_module_branch_model_field_action2"
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        action["name"] = _("Parent Fields")
        action["domain"] = [("id", "in", self.parent_ids.ids)]
        action["context"] = {}
        return action

    def _to_dict(self):
        self.ensure_one()
        return {
            "name": self.name,
            "field_type": self.field_type,
        }
