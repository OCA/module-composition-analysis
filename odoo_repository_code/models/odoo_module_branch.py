# Copyright 2025 Sebastien Alix <https://github.com/sebalix>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models


class OdooModuleBranch(models.Model):
    _inherit = "odoo.module.branch"

    model_ids = fields.One2many(
        comodel_name="odoo.module.branch.model",
        inverse_name="module_branch_id",
        string="Models",
    )
    models_count = fields.Integer(compute="_compute_models_count")
    data_ids = fields.One2many(
        comodel_name="odoo.module.branch.data",
        inverse_name="module_branch_id",
        string="Data",
    )
    data_count = fields.Integer(compute="_compute_data_count")

    @api.depends("model_ids")
    def _compute_models_count(self):
        for rec in self:
            rec.models_count = len(rec.model_ids)

    @api.depends("data_ids")
    def _compute_data_count(self):
        for rec in self:
            rec.data_count = len(rec.data_ids)

    def open_models(self):
        self.ensure_one()
        xml_id = "odoo_repository_code.odoo_module_branch_model_action"
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        action["name"] = _("Models")
        action["domain"] = [("id", "in", self.model_ids.ids)]
        action["context"] = {}
        return action

    def open_data(self):
        self.ensure_one()
        xml_id = "odoo_repository_code.odoo_module_branch_data_action"
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        action["name"] = _("Data")
        action["domain"] = [("id", "in", self.data_ids.ids)]
        action["context"] = {}
        return action

    def push_scanned_data(self, repo_branch_id, module, data):
        module_branch = super().push_scanned_data(repo_branch_id, module, data)
        module_branch._import_code(data)
        return module_branch

    def _import_code(self, data):
        self.ensure_one()
        # Import Odoo data models only if the module is installable
        if data.get("models") and self.installable:
            self._import_code_odoo_models(data["models"])
        else:
            self._cleanup_code_odoo_models()
        # Import module data (XML/CSV records) only if the module is installable
        if (data.get("data") or data.get("demo")) and self.installable:
            self._import_code_odoo_data(data.get("data") or {}, data.get("demo") or {})
        else:
            self._cleanup_code_odoo_data()

    def _import_code_odoo_models(self, data_models):
        self.ensure_one()
        # These are entries created/updated from scanned module
        mb_model_ids = []
        mb_model_field_ids = []
        mb_model_method_ids = []
        for model_name, data in data_models.items():
            odoo_model = self._get_or_create_odoo_model(model_name, data)
            odoo_model_version = self._get_or_create_odoo_model_version(odoo_model)
            vals = self._prepare_odoo_module_branch_model_values(
                odoo_model_version, data
            )
            mb_model = self._create_or_update_odoo_module_branch_model(vals)
            mb_model_ids.append(mb_model.id)
            # Import fields
            for field_data in data.get("fields", {}).values():
                vals = self._prepare_odoo_module_branch_model_field_values(
                    mb_model, field_data
                )
                field_ = self._create_or_update_odoo_module_branch_model_field(vals)
                mb_model_field_ids.append(field_.id)
            # Import methods
            for method_data in data.get("methods", {}).values():
                vals = self._prepare_odoo_module_branch_model_method_values(
                    mb_model, method_data
                )
                method = self._create_or_update_odoo_module_branch_model_method(vals)
                mb_model_method_ids.append(method.id)
        self._archive_code_elements(
            mb_model_ids, mb_model_field_ids, mb_model_method_ids
        )

    def _cleanup_code_odoo_models(self):
        self.ensure_one()
        self.model_ids.sudo().unlink()

    def _archive_code_elements(
        self, scanned_model_ids, scanned_field_ids, scanned_method_ids
    ):
        """Archive code elements that doesn't exist anymore."""
        models = (
            self.model_ids
            - self.env["odoo.module.branch.model"].browse(scanned_model_ids).sudo()
        )
        fields = (
            self.model_ids.field_ids
            - self.env["odoo.module.branch.model.field"]
            .browse(scanned_field_ids)
            .sudo()
        )
        methods = (
            self.model_ids.method_ids
            - self.env["odoo.module.branch.model.method"]
            .browse(scanned_method_ids)
            .sudo()
        )
        models.active = fields.active = methods.active = False

    def _prepare_odoo_module_branch_model_values(self, odoo_model_version, data):
        self.ensure_one()
        # Handle custom types
        model_type = data["type"]
        available_types = [
            elt[0]
            for elt in self.env["odoo.module.branch.model"]
            ._fields["model_type"]
            .selection
        ]
        if model_type not in available_types:
            model_type = "Other"
        return {
            "module_branch_id": self.id,
            "odoo_model_version_id": odoo_model_version.id,
            "data": data,
            "model_type": model_type,
            "active": True,
        }

    def _create_or_update_odoo_module_branch_model(self, vals):
        self.ensure_one()
        rec = self.env["odoo.module.branch.model"].search(
            [
                ("module_branch_id", "=", vals["module_branch_id"]),
                ("odoo_model_version_id", "=", vals["odoo_model_version_id"]),
            ]
        )
        if rec:
            rec.sudo().write(vals)
        else:
            rec = self.env["odoo.module.branch.model"].sudo().create(vals)
        return rec

    def _get_or_create_odoo_model(self, model_name, data):
        self.ensure_one()
        rec = self.env["odoo.model"].search([("name", "=", model_name)], limit=1)
        if not rec:
            vals = {"name": model_name}
            rec = self.env["odoo.model"].sudo().create(vals)
        return rec

    def _get_or_create_odoo_model_version(self, odoo_model):
        self.ensure_one()
        rec = self.env["odoo.model.version"].search(
            [
                ("odoo_model_id", "=", odoo_model.id),
                ("odoo_version_id", "=", self.branch_id.id),
            ],
            limit=1,
        )
        if not rec:
            vals = {
                "odoo_model_id": odoo_model.id,
                "odoo_version_id": self.branch_id.id,
            }
            rec = self.env["odoo.model.version"].sudo().create(vals)
        return rec

    # == fields import ==

    def _prepare_odoo_module_branch_model_field_values(self, module_branch_model, data):
        self.ensure_one()
        return {
            "module_branch_model_id": module_branch_model.id,
            "name": data["name"],
            "data": data,
            "field_type": data["type"],
            "active": True,
        }

    def _create_or_update_odoo_module_branch_model_field(self, vals):
        self.ensure_one()
        model_ = self.env["odoo.module.branch.model.field"]
        rec = model_.search(
            [
                ("module_branch_model_id", "=", vals["module_branch_model_id"]),
                ("name", "=", vals["name"]),
            ],
            limit=1,
        )
        if rec:
            rec.sudo().write(vals)
        else:
            rec = model_.sudo().create(vals)
        return rec

    # == methods import ==

    def _prepare_odoo_module_branch_model_method_values(
        self, module_branch_model, data
    ):
        self.ensure_one()
        return {
            "module_branch_model_id": module_branch_model.id,
            "name": data["name"],
            "data": data,
            "active": True,
        }

    def _create_or_update_odoo_module_branch_model_method(self, vals):
        self.ensure_one()
        model_ = self.env["odoo.module.branch.model.method"]
        rec = model_.search(
            [
                ("module_branch_model_id", "=", vals["module_branch_model_id"]),
                ("name", "=", vals["name"]),
            ],
            limit=1,
        )
        if rec:
            rec.sudo().write(vals)
        else:
            rec = model_.sudo().create(vals)
        return rec

    # == data import ==

    def _import_code_odoo_data(self, data_records, demo_records):
        self.ensure_one()
        # These are entries created/updated from scanned module
        mb_data_ids = []
        for data_type, records in (("data", data_records), ("demo", demo_records)):
            for model_name, model_records in records.items():
                odoo_model = self._get_or_create_odoo_model(model_name, None)
                odoo_model_version = self._get_or_create_odoo_model_version(odoo_model)
                for record in model_records:
                    vals = self._prepare_odoo_module_branch_data_values(
                        odoo_model_version, record, data_type
                    )
                    data_ = self._create_or_update_odoo_module_branch_data(vals)
                    mb_data_ids.append(data_.id)
        self._archive_code_data_elements(mb_data_ids)

    def _cleanup_code_odoo_data(self):
        self.ensure_one()
        self.data_ids.sudo().unlink()

    def _archive_code_data_elements(self, scanned_data_ids):
        """Archive data elements that doesn't exist anymore."""
        data = (
            self.data_ids
            - self.env["odoo.module.branch.data"].browse(scanned_data_ids).sudo()
        )
        data.active = False

    def _prepare_odoo_module_branch_data_values(
        self, odoo_model_version, record, data_type
    ):
        self.ensure_one()
        return {
            "module_branch_id": self.id,
            "odoo_model_version_id": odoo_model_version.id,
            "xml_id": record["id"],
            "name": record.get("name") or record["id"],
            "file_path": record.get("file_path"),
            "data_type": data_type,
            "loaded": record.get("loaded", False),
            "noupdate": record.get("noupdate", False),
            "data": record,
            "active": True,
        }

    def _create_or_update_odoo_module_branch_data(self, vals):
        self.ensure_one()
        model_ = self.env["odoo.module.branch.data"].with_context(active_test=False)
        rec = model_.search(
            [
                ("module_branch_id", "=", vals["module_branch_id"]),
                ("odoo_model_version_id", "=", vals["odoo_model_version_id"]),
                ("xml_id", "=", vals["xml_id"]),
                ("data_type", "=", vals["data_type"]),
            ],
            limit=1,
        )
        if rec:
            rec.sudo().write(vals)
        else:
            rec = model_.sudo().create(vals)
        return rec

    def _to_dict(self):
        data = super()._to_dict()
        data["models"] = [model._to_dict() for model in self.model_ids]
        # Group data records by type and model
        for data_type in ("data", "demo"):
            data_records = self.data_ids.filtered(
                lambda rec, data_type=data_type: rec.data_type == data_type
            )
            if data_records:
                data[data_type] = {}
                for rec in data_records:
                    data[data_type].setdefault(rec.odoo_model_name, []).append(
                        rec._to_dict()
                    )
        return data
