# Copyright 2026 Sebastien Alix <https://github.com/sebalix>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json

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
    xml_id = fields.Char(string="Module ID", required=True, index="trigram")
    full_xml_id = fields.Char(
        string="External ID",
        compute="_compute_full_xml_id",
        store=True,
        index="trigram",
    )
    is_override = fields.Boolean(
        compute="_compute_is_override",
        store=True,
    )
    overridden_id = fields.Many2one(
        comodel_name="odoo.module.branch.data",
        string="Overridden Data",
        compute="_compute_overridden_id",
        help="Previous definition of this record based on module dependencies.",
    )
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
    data_json = fields.Text(compute="_compute_data_json")
    data_xml = fields.Text(
        string="XML Source",
        compute="_compute_data_xml",
        help="Raw XML source of the record, as written in the file "
        "(empty for CSV records).",
    )
    active = fields.Boolean(default=True)

    @api.depends("odoo_model_name", "xml_id", "module_branch_id")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = (
                f"{rec.full_xml_id} in {rec.module_branch_id.display_name}"
            )

    @api.depends("module_name", "xml_id")
    def _compute_full_xml_id(self):
        for rec in self:
            rec.full_xml_id = rec.xml_id
            if "." not in rec.xml_id:
                rec.full_xml_id = f"{rec.module_name}.{rec.xml_id}"

    @api.depends("module_name", "xml_id")
    def _compute_is_override(self):
        for rec in self:
            prefix, sep, _tail = rec.xml_id.partition(".")
            rec.is_override = bool(sep and prefix and prefix != rec.module_name)

    @api.depends("is_override", "odoo_version_id")
    def _compute_overridden_id(self):
        for rec in self:
            rec.overridden_id = rec._find_previous_overridden_record()

    def _find_previous_overridden_record(self):
        """Return the previous definition of the overriden record."""
        self.ensure_one()
        if not self.is_override:
            return self.browse()
        candidates = self.with_context(active_test=True).search(
            [
                ("id", "!=", self.id),
                ("full_xml_id", "=", self.xml_id),
                ("odoo_version_id", "=", self.odoo_version_id.id),
                ("module_name", "!=", self.module_name),
            ],
            order="global_dependency_level DESC, id ASC",
        )
        dependency_ids = set(self.module_branch_id._get_recursive_dependencies().ids)
        # The result may be empty if the dependencies haven't been scanned yet
        return candidates.filtered(
            lambda rec: rec.module_branch_id.id in dependency_ids
        )[:1]

    def _to_dict(self):
        self.ensure_one()
        return dict(self.data)

    @api.depends("data")
    def _compute_data_json(self):
        for rec in self:
            # The raw XML source is displayed in the 'data_xml' field
            data = (
                {key: val for key, val in rec.data.items() if key != "xml"}
                if rec.data
                else False
            )
            rec.data_json = (
                json.dumps(data, indent=4, sort_keys=True) if data else False
            )

    @api.depends("data")
    def _compute_data_xml(self):
        for rec in self:
            rec.data_xml = rec.data.get("xml", False) if rec.data else False
