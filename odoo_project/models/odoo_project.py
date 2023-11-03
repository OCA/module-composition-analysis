# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import ast

from odoo import api, fields, models


class OdooProject(models.Model):
    _name = "odoo.project"
    _inherits = {"odoo.repository": "repository_id"}
    _description = "Odoo Project"
    _order = "name"

    name = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    repository_id = fields.Many2one(
        comodel_name="odoo.repository",
        ondelete="restrict",
        string="Repository",
        domain=[
            ("clone_branch_id", "!=", False),
            ("odoo_version_id", "!=", False),
        ],
        required=True,
    )
    project_module_ids = fields.One2many(
        comodel_name="odoo.project.module",
        inverse_name="odoo_project_id",
        string="Deployed Modules",
    )
    module_ids = fields.Many2many(
        comodel_name="odoo.module",
        relation="odoo_project_module_rel",
        column1="odoo_project_id",
        column2="module_id",
        string="Modules",
        compute="_compute_module_ids",
        store=True,
    )
    modules_count = fields.Integer(compute="_compute_modules_count")
    module_not_installed_ids = fields.Many2many(
        comodel_name="odoo.module.branch",
        string="Modules not installed",
        help="Modules available in the project repository but not installed.",
        compute="_compute_module_not_installed_ids",
    )
    unmerged_module_ids = fields.Many2many(
        comodel_name="odoo.module.branch",
        string="Modules to merge",
        help="Modules installed belonging to an open PR.",
        compute="_compute_unmerged_module_ids",
    )
    unknown_module_ids = fields.Many2many(
        comodel_name="odoo.module.branch",
        string="Modules unknown",
        help="Modules installed but cannot be found among repositories/branches.",
        compute="_compute_unknown_module_ids",
    )

    @api.depends("project_module_ids.module_id")
    def _compute_module_ids(self):
        for rec in self:
            rec.module_ids = rec.project_module_ids.module_id.ids

    @api.depends("project_module_ids")
    def _compute_modules_count(self):
        for rec in self:
            rec.modules_count = len(rec.project_module_ids)

    @api.depends(
        "repository_id.branch_ids.module_ids", "project_module_ids.module_branch_id"
    )
    def _compute_module_not_installed_ids(self):
        for rec in self:
            all_module_ids = set(rec.repository_id.branch_ids.module_ids.ids)
            installed_module_ids = set(rec.project_module_ids.module_branch_id.ids)
            rec.module_not_installed_ids = list(all_module_ids - installed_module_ids)

    @api.depends("project_module_ids.pr_url")
    def _compute_unmerged_module_ids(self):
        for rec in self:
            rec.unmerged_module_ids = rec.project_module_ids.module_branch_id.filtered(
                lambda module: module.pr_url
            )

    @api.depends("project_module_ids.repository_id")
    def _compute_unknown_module_ids(self):
        for rec in self:
            rec.unknown_module_ids = rec.project_module_ids.module_branch_id.filtered(
                lambda module: not module.repository_id
            )

    def open_import_modules(self):
        """Open a wizard to import the modules of this Odoo project."""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "odoo_project.odoo_project_import_modules_action"
        )
        ctx = action.get("context", {})
        if isinstance(ctx, str):
            ctx = ast.literal_eval(ctx)
        ctx["default_odoo_project_id"] = self.id
        action["context"] = ctx
        return action

    def open_modules(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "odoo_project.odoo_project_module_action"
        )
        ctx = action.get("context", {})
        if isinstance(ctx, str):
            ctx = ast.literal_eval(ctx)
        action["domain"] = [("id", "in", self.project_module_ids.ids)]
        ctx["search_default_group_by_org_id"] = 1
        ctx["search_default_group_by_repository_id"] = 2
        action["context"] = ctx
        return action
