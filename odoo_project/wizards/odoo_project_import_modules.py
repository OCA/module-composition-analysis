# Copyright 2023 Camptocamp SA
# Copyright 2026 ACSONE SA/NV (<https://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import re

from odoo import api, fields, models


class OdooProjectImportModules(models.TransientModel):
    _name = "odoo.project.import.modules"
    _description = "Import modules for an Odoo project"

    odoo_project_id = fields.Many2one(
        comodel_name="odoo.project",
        string="Project",
        required=True,
    )
    odoo_version_id = fields.Many2one(related="odoo_project_id.odoo_version_id")
    additional_module_ids = fields.Many2many(
        comodel_name="odoo.module.branch",
        string="Additional Modules",
        domain="[('branch_id', '=', odoo_version_id), ('repository_id', '!=', False)]",
    )
    modules_list = fields.Text(
        help=(
            "Copy/paste your list of technical module names here.\n"
            "One module per line with an optional version number (separated by "
            "any special character (space, tabulation, comma...)."
        ),
    )
    import_missing_dependencies = fields.Boolean(
        default=False,
        help=(
            "Import module dependencies that are not part of the list above "
            "to get an exhaustive list of modules installed in the project."
        ),
    )

    @api.onchange("additional_module_ids")
    def _onchange_additional_module_ids(self):
        if self.additional_module_ids:
            self.import_missing_dependencies = True

    def action_import(self):
        """Import the modules for the given Odoo project."""
        self.ensure_one()
        project_module_ids = []
        if self.modules_list:
            project_module_ids = self._action_import_modules_list()
        project_module_ids.extend(self._action_import_additional_modules())
        if self.import_missing_dependencies:
            project_modules = self.env["odoo.project.module"].browse(project_module_ids)
            self.odoo_project_id._import_missing_dependencies(project_modules)

    def _action_import_modules_list(self):
        """Import a fresh list of installed modules into the project."""
        project = self.odoo_project_id
        project.sudo().project_module_ids = False
        module_lines = list(filter(None, self.modules_list.split("\n")))
        project_module_ids = []
        for line in module_lines:
            # Ignore comments
            if line.strip().startswith("#"):
                continue
            data = re.split(r"\W+", line, maxsplit=1)
            if len(data) > 1:
                module_name, version = data
            else:
                module_name, version = data[0], False
            # for module_name in module_names:
            module = self.env["odoo.module.branch"]._get_module(module_name)
            if module.blacklisted:
                continue
            module_branch = project._get_module_branch(module)
            project_module = project._get_project_module(module_branch, version)
            project_module_ids.append(project_module.id)
        project.sudo().project_module_ids = project_module_ids
        return project_module_ids

    def _action_import_additional_modules(self):
        """Import additional modules into the project."""
        project_module_ids = []
        for module_branch in self.additional_module_ids:
            project_module = self.odoo_project_id._get_project_module(
                module_branch, version=False
            )
            project_module_ids.append(project_module.id)
        return project_module_ids
