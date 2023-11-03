# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import re

from odoo import fields, models


class OdooProjectImportModules(models.TransientModel):
    _name = "odoo.project.import.modules"
    _description = "Import modules for an Odoo project"

    odoo_project_id = fields.Many2one(
        comodel_name="odoo.project",
        string="Project",
        required=True,
    )
    modules_list = fields.Text(
        help=(
            "Copy/paste your list of technical module names here.\n"
            "One module per line, with an optional version number placed "
            "after the module name separated by any special character "
            "(space, tabulation, comma...)."
        ),
        required=True,
    )

    def action_import(self):
        """Import the modules for the given Odoo project."""
        self.ensure_one()
        self.odoo_project_id.sudo().project_module_ids = False
        module_lines = list(filter(None, self.modules_list.split("\n")))
        # module_names = (
        #     re.split(r"\W+", self.modules_list) if self.modules_list else []
        # )
        # module_names = list(filter(None, module_names))
        project_module_ids = []
        for line in module_lines:
            data = re.split(r"\W+", line, maxsplit=1)
            if len(data) > 1:
                module_name, version = data
            else:
                module_name, version = data[0], False
            # for module_name in module_names:
            module = self._get_module(module_name)
            module_branch = self._get_module_branch(module)
            project_module = self._get_project_module(module_branch, version)
            project_module_ids.append(project_module.id)
        self.odoo_project_id.sudo().project_module_ids = project_module_ids
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
        args = [
            ("module_id", "=", module.id),
            ("branch_id", "=", self.odoo_project_id.odoo_version_id.id),
        ]
        module_branch = module_branch_model.search(args)
        if not module_branch:
            # Create the module
            branch = self.odoo_project_id.odoo_version_id
            values = {
                "module_id": module.id,
                "branch_id": branch.id,
            }
            module_branch = module_branch_model.sudo().create(values)
        if not module_branch.repository_branch_id:
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
        args = [
            ("module_branch_id", "=", module_branch.id),
            ("odoo_project_id", "=", self.odoo_project_id.id),
        ]
        project_module = project_module_model.search(args)
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
