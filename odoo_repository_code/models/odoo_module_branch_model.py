# Copyright 2025 Sebastien Alix <https://github.com/sebalix>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
import psycopg2.sql as pgsql
from markupsafe import Markup
from odoo_addons_parser.code import BASE_CLASSES

from odoo import _, api, fields, models
from odoo.osv.expression import SQL_OPERATORS
from odoo.tools.safe_eval import safe_eval


class OdooModuleBranchModel(models.Model):
    _name = "odoo.module.branch.model"
    _description = "Odoo model"
    _order = (
        "repository_sequence, odoo_model_name, "
        "odoo_version_sequence DESC, global_dependency_level, module_name"
    )

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
    odoo_version_sequence = fields.Integer(
        related="module_branch_id.branch_id.sequence",
        store=True,
        string="Odoo Version Sequence",
    )
    org_id = fields.Many2one(related="module_branch_id.org_id", store=True, index=True)
    repository_id = fields.Many2one(
        related="module_branch_id.repository_id", store=True, index=True
    )
    repository_sequence = fields.Integer(
        related="module_branch_id.repository_id.sequence",
        store=True,
        string="Repository Sequence",
    )
    global_dependency_level = fields.Integer(
        string="Dep. Level",
        related="module_branch_id.global_dependency_level",
        store=True,
    )
    display_name = fields.Char(
        compute="_compute_display_name", store=True, index="trigram"
    )
    active = fields.Boolean(default=True)
    data = fields.Serialized()
    model_type = fields.Selection(
        selection=[
            ("AbstractModel", "AbstractModel"),
            ("Model", "Model"),
            ("TransientModel", "TransientModel"),
            ("Other", "Other"),
        ],
        string="Type",
        default="Model",
        required=True,
        index=True,
    )
    order = fields.Char()
    field_ids = fields.One2many(
        comodel_name="odoo.module.branch.model.field",
        inverse_name="module_branch_model_id",
        string="Fields",
    )
    method_ids = fields.One2many(
        comodel_name="odoo.module.branch.model.method",
        inverse_name="module_branch_model_id",
        string="Methods",
    )
    root_id = fields.Many2one(
        string="Origin",
        comodel_name="odoo.module.branch.model",
        compute="_compute_root_id",
        recursive=True,
    )
    root_warning = fields.Html(compute="_compute_root_id")
    inherit_ids = fields.Many2many(
        comodel_name="odoo.model.version",
        compute="_compute_inherit_ids",
        search="_search_inherit_ids",
    )
    inherits_ids = fields.Many2many(
        comodel_name="odoo.model.version",
        compute="_compute_inherits_ids",
        search="_search_inherits_ids",
    )
    next_odoo_version_model_id = fields.Many2one(
        comodel_name="odoo.module.branch.model",
        compute="_compute_next_odoo_version_model_id",
    )

    @api.depends("odoo_model_id", "module_branch_id")
    def _compute_display_name(self):
        for rec in self:
            model_name = rec.odoo_model_id.name
            if model_name not in BASE_CLASSES:
                model_name = f"<{model_name}>"
            rec.display_name = f"{model_name} in {rec.module_branch_id.display_name}"

    @api.depends("data")
    def _compute_inherit_ids(self):
        for rec in self:
            rec.inherit_ids = False
            inherit = safe_eval(repr(rec.data.get("inherit")))
            if isinstance(inherit, str):
                inherit = [inherit]
            if inherit:
                models = self.env["odoo.model.version"].search(
                    [
                        ("odoo_model_id", "in", inherit),
                        ("odoo_version_id", "=", rec.odoo_version_id.id),
                    ]
                )
                rec.inherit_ids = models

    def _search_inherit_ids(self, operator, value):
        sql_operator = SQL_OPERATORS[operator].code
        query = pgsql.SQL(
            """
                SELECT array_agg(id)
                FROM {table}
                WHERE data::json->>'inherit' {operator} %s;
            """
        )
        query = query.format(
            table=pgsql.Identifier(self._table),
            operator=pgsql.SQL(sql_operator),
        )
        args = (f"%{value}%",)
        self.env.cr.execute(query, args)
        model_ids = self.env.cr.fetchone()[0] or []
        return [("id", "in", model_ids)]

    @api.depends("data")
    def _compute_inherits_ids(self):
        for rec in self:
            rec.inherits_ids = False
            if not rec.data.get("inherits"):
                continue
            inherits_list = list(rec.data["inherits"])
            inherits = [safe_eval(elt) for elt in inherits_list]
            if inherits:
                models = self.env["odoo.model.version"].search(
                    [
                        ("odoo_model_id", "in", list(inherits)),
                        ("odoo_version_id", "=", rec.odoo_version_id.id),
                    ]
                )
                rec.inherits_ids = models

    def _search_inherits_ids(self, operator, value):
        sql_operator = SQL_OPERATORS[operator].code
        query = pgsql.SQL(
            """
                SELECT array_agg(id)
                FROM {table}
                WHERE data::json->>'inherits' {operator} %s;
            """
        )
        query = query.format(
            table=pgsql.Identifier(self._table),
            operator=pgsql.SQL(sql_operator),
        )
        args = (f"%{value}%",)
        self.env.cr.execute(query, args)
        model_ids = self.env.cr.fetchone()[0] or []
        return [("id", "in", model_ids)]

    @api.depends("odoo_model_version_id")
    def _compute_root_id(self):
        for rec in self:
            root = rec.search(
                [("odoo_model_version_id", "=", rec.odoo_model_version_id.id)],
                order="global_dependency_level",
                limit=1,
            )
            rec.root_id = root if root != rec else False
            # Warning if the root module is not found in known dependencies
            rec.root_warning = False
            deps = rec.module_branch_id._get_recursive_dependencies()
            if (
                rec.root_id
                and root.module_branch_id not in deps
                # All modules are depending on base even if not listed,
                # no need to display a warning in such case
                and rec.root_id.module_name != "base"
            ):
                rec.root_warning = _(
                    Markup(
                        "<b>{root}</b> is not in the known dependencies "
                        "of <b>{module}</b>."
                    )
                ).format(root=rec.root_id.module_name, module=rec.module_name)

    def _get_parent_models(self, include_self=False):
        """Return all parent models, sorted by level of dependency.

        This is based on actual dependencies of current module.
        """
        self.ensure_one()
        # Get all dependencies of current module (including self)
        dependencies = self.module_branch_id._get_recursive_dependencies()
        dependencies |= self.module_branch_id
        # Collect parent models recursively
        # NOTE: includes base models
        parent_model_ids = self.search(
            [
                ("odoo_version_id", "=", self.odoo_version_id.id),
                ("odoo_model_name", "in", BASE_CLASSES),
            ]
        ).ids
        visited = set()

        def collect_parents(current_model, parent_model_ids=parent_model_ids):
            if current_model.id in visited:
                return
            visited.add(current_model.id)

            # For each model version this model inherits from
            all_inherits = current_model.inherit_ids | current_model.inherits_ids
            for model_version in all_inherits:
                # Find implementations of this model version in dependencies
                implementations = self.search(
                    [
                        ("odoo_model_version_id", "=", model_version.id),
                        ("module_branch_id", "in", dependencies.ids),
                    ]
                )
                for impl in implementations:
                    if impl.id not in parent_model_ids:
                        parent_model_ids.append(impl.id)
                        collect_parents(impl, parent_model_ids=parent_model_ids)

        collect_parents(self, parent_model_ids=parent_model_ids)
        # Remove self from results
        if not include_self and self.id in parent_model_ids:
            parent_model_ids.remove(self.id)
        # Sort by dependency level (lower levels first = base modules first)
        return self.search(
            [("id", "in", parent_model_ids)], order="global_dependency_level"
        )

    @api.depends("odoo_version_id.next_id")
    def _compute_next_odoo_version_model_id(self):
        for rec in self:
            rec.next_odoo_version_model_id = False
            # Stop there if no next version
            if not rec.odoo_version_id.next_id:
                continue
            # Look for the next available version for this module name
            rec.next_odoo_version_model_id = self.search(
                [
                    (
                        "odoo_version_sequence",
                        ">=",
                        rec.odoo_version_id.next_id.sequence,
                    ),
                    ("odoo_model_id", "=", rec.odoo_model_id.id),
                ],
                order="odoo_version_sequence,global_dependency_level",
                limit=1,
            )
            # # Stop there if no renaming/relacement
            # if not rec.timeline_ids:
            #     continue
            # rec.next_odoo_version_module_branch_id = self.search(
            #     [
            #         ("branch_sequence", ">=", rec.branch_id.next_id.sequence),
            #         ("module_id", "=", rec.timeline_ids.next_module_id.id),
            #     ],
            #     order="branch_sequence",
            #     limit=1,
            # )

    def open_next_odoo_version_model(self):
        self.ensure_one()
        xml_id = "odoo_repository_code.odoo_module_branch_model_action"
        if not self.next_odoo_version_model_id:
            return False
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        action["name"] = _("Next version")
        # action["domain"] = [("id", "=", self.next_odoo_version_model_id.id)]
        del action["view_id"]  # = (468, 'odoo.module.branch.model.tree'),
        action["view_mode"] = "form"
        action["views"] = [(False, "form")]
        action["res_id"] = self.next_odoo_version_model_id.id
        return action

    def open_parent_models(self):
        self.ensure_one()
        parent_models = self._get_parent_models(include_self=True)
        xml_id = "odoo_repository_code.odoo_module_branch_model_action"
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        action["name"] = _("Parent Models")
        action["domain"] = [("id", "in", parent_models.ids)]
        action["context"] = {}
        return action

    def _to_dict(self):
        self.ensure_one()
        return {
            "name": self.odoo_model_name,
            "inherit": self.inherit_ids.odoo_model_id.mapped("name"),
            "inherits": self.inherits_ids.odoo_model_id.mapped("name"),
            "type": self.model_type,
            "order": self.order,
            "fields": [rec._to_dict() for rec in self.field_ids],
            "methods": [rec._to_dict() for rec in self.method_ids],
        }
