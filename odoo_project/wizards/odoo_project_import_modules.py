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
        string="Modules List",
        help=(
            "Copy/paste your list of technical module names here.\n"
            "They can be separated by spaces, tabulations, comma or any other "
            "special characters."
        ),
        required=True,
    )

    def action_import(self):
        """Import the modules for the given Odoo project."""
        self.ensure_one()
        self.odoo_project_id.module_branch_ids = False
        module_names = (
            re.split(r"\W+", self.modules_list) if self.modules_list else []
        )
        module_names = list(filter(None, module_names))
        module_branch_ids = []
        for module_name in module_names:
            module = self._get_module(module_name)
            module_branch = self._get_module_branch(module)
            module_branch_ids.append(module_branch.id)
        self.odoo_project_id.module_branch_ids = module_branch_ids
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
        """Return a `odoo.module.branch` record for the project.

        If it doesn't exist it'll be automatically created.
        """
        module_branch_model = self.env["odoo.module.branch"]
        args = [
            ("module_id", "=", module.id),
            ("branch_id", "=", self.odoo_project_id.odoo_version_id.id),
        ]
        module_branch = module_branch_model.search(args)
        if not module_branch:
            # Create the module to make it available for the project
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
