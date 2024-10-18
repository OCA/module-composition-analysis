# Copyright 2023 Camptocamp SA
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
            self._action_import_missing_dependencies(project_module_ids)

    def _action_import_modules_list(self):
        """Import a fresh list of installed modules into the project."""
        self.odoo_project_id.sudo().project_module_ids = False
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
            module = self._get_module(module_name)
            if module.blacklisted:
                continue
            module_branch = self._get_module_branch(module)
            project_module = self._get_project_module(module_branch, version)
            project_module_ids.append(project_module.id)
        self.odoo_project_id.sudo().project_module_ids = project_module_ids
        return project_module_ids

    def _action_import_additional_modules(self):
        """Import additional modules into the project."""
        project_module_ids = []
        for module_branch in self.additional_module_ids:
            project_module = self._get_project_module(module_branch, version=False)
            project_module_ids.append(project_module.id)
        return project_module_ids

    def _action_import_missing_dependencies(self, project_module_ids):
        """Complete list of modules by adding all dependencies."""
        project_modules = self.env["odoo.project.module"].browse(project_module_ids)
        branch_modules = project_modules.module_branch_id
        all_dependencies = branch_modules._get_recursive_dependencies()
        missing_dependencies = all_dependencies - branch_modules
        for missing_dependency in missing_dependencies:
            self._get_project_module(missing_dependency, missing_dependency.version)
        return True

    def _get_module(self, module_name):
        """Return a `odoo.module` record.

        If it doesn't exist it'll be automatically created.
        """
        module_model = self.env["odoo.module"]
        module = module_model.search([("name", "=", module_name)])
        if not module:
            module = module_model.sudo().create({"name": module_name})
        return module

    def _get_module_branch(self, module):
        """Return a `odoo.module.branch` record.

        If it doesn't exist it'll be automatically created.
        """
        module_branch_model = self.env["odoo.module.branch"]
        module_branch = False
        branch = self.odoo_project_id.odoo_version_id
        module_branch = module_branch_model._find_or_create(
            branch, module, self.odoo_project_id.repository_id
        )
        if not module_branch.repository_branch_id and not module_branch.specific:
            # If the module hasn't been found in existing repositories content,
            # it could be available somewhere on GitHub as a PR that could help
            # to identity its repository
            module_branch.with_delay().action_find_pr_url()
        return module_branch

    def _get_project_module(self, module_branch, version):
        """Return a `odoo.project.module` record for the project.

        If it doesn't exist it'll be automatically created.
        """
        project_module_model = self.env["odoo.project.module"]
        domain = [
            ("module_branch_id", "=", module_branch.id),
            ("odoo_project_id", "=", self.odoo_project_id.id),
        ]
        project_module = project_module_model.search(domain)
        values = {
            "module_branch_id": module_branch.id,
            "odoo_project_id": self.odoo_project_id.id,
            "installed_version": version,
        }
        if project_module:
            project_module.sudo().write(values)
        else:
            # Create the module to make it available for the project
            project_module = project_module_model.sudo().create(values)
        return project_module
