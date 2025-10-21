# Copyright 2025 Sebastien Alix <https://github.com/sebalix>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class OdooModuleBranchModelField(models.Model):
    _name = "odoo.module.branch.model.field"
    _description = "Odoo field"

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
    name = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    field_type = fields.Char(string="Type", required=True, index=True)
    data = fields.Serialized()
    code = fields.Text(compute="_compute_code", store=True, index="trigram")
    comodel_name = fields.Char(compute="_compute_comodel_name", store=True, index=True)
    comodel_id = fields.Many2one(
        comodel_name="odoo.model.version",
        compute="_compute_comodel_id",
    )
    is_relational = fields.Boolean(compute="_compute_is_relational", store=True)
    is_computed = fields.Boolean(compute="_compute_is_computed", store=True)
    is_readonly = fields.Boolean(compute="_compute_is_readonly", store=True)
    is_required = fields.Boolean(compute="_compute_is_required", store=True)
    is_stored = fields.Boolean(compute="_compute_is_stored", store=True)
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
    def _compute_is_computed(self):
        for rec in self:
            # Default: only computed
            rec.is_computed = False
            kwargs = rec.data.get("kwargs", {})
            # Case of onchange computed field => we do not consider it as computed
            if (
                kwargs.get("compute")
                and kwargs.get("readonly") is False
                and kwargs.get("store")
            ):
                continue
            rec.is_computed = kwargs.get("compute") or kwargs.get("related")

    @api.depends("data")
    def _compute_is_readonly(self):
        for rec in self:
            # Default: not readonly
            rec.is_readonly = False
            kwargs = rec.data.get("kwargs", {})
            # Simple case: 'readonly' attribute manually set
            if "readonly" in kwargs:
                rec.is_readonly = kwargs["readonly"]
            # Computed field without inverse
            elif kwargs.get("compute") and not kwargs.get("inverse"):
                rec.is_readonly = True
            # Related field
            elif kwargs.get("related"):
                rec.is_readonly = True

    @api.depends("data")
    def _compute_is_required(self):
        for rec in self:
            # Default: not required
            rec.is_required = False
            kwargs = rec.data.get("kwargs", {})
            # Simple case: 'required' attribute manually set
            if "required" in kwargs:
                rec.is_required = kwargs["required"]

    @api.depends("data")
    def _compute_is_stored(self):
        for rec in self:
            # Default: stored
            rec.is_stored = True
            kwargs = rec.data.get("kwargs", {})
            # Simple case: 'store' attribute manually set
            if "store" in kwargs:
                rec.is_stored = kwargs["store"]
            # Computed or related field
            elif kwargs.get("compute") or kwargs.get("related"):
                rec.is_stored = False

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

    def _to_dict(self):
        self.ensure_one()
        return {
            "name": self.name,
            "field_type": self.field_type,
        }
