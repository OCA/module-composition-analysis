# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class OdooModuleBranch(models.Model):
    _inherit = "odoo.module.branch"

    odoo_project_module_ids = fields.One2many(
        comodel_name="odoo.project.module",
        inverse_name="module_branch_id",
        string="Deployed Modules",
    )
    odoo_project_ids = fields.Many2many(
        comodel_name="odoo.project",
        relation="odoo_project_module_branch_rel",
        column1="module_branch_id",
        column2="odoo_project_id",
        string="Projects",
        compute="_compute_module_ids",
        store=True,
    )

    @api.depends("odoo_project_module_ids.odoo_project_id")
    def _compute_module_ids(self):
        for rec in self:
            rec.odoo_project_ids = rec.odoo_project_module_ids.odoo_project_id.ids

    def _filter_module_to_update(self, repo_branch, module_branch):
        # A module found in a specific repository cannot be linked to an orphaned
        # module that is already listed/installed in different projects (chances
        # are these projects refer to a generic version of the module).
        # For such specific module we want to create a dedicated 'odoo.module.branch'.
        if (
            repo_branch.repository_id.specific
            # Orphaned module
            and module_branch
            and not module_branch.repository_id
            # Installed in multiple projects
            # NOTE: we could have multiple project instances using the same
            # repository, so we check the underlying repo instead
            and len(module_branch.odoo_project_ids.repository_id) > 1
        ):
            repo_projects = repo_branch.repository_id.project_ids
            if repo_projects:
                # Corner case: if the current project(s) are referring to this
                # orphaned module, remove them as they will now have a dedicated
                # specific module created.
                # Spawn a job to re-map project modules to the new (not yet created)
                # specific module.
                project_modules = module_branch.odoo_project_module_ids.filtered(
                    lambda o: o.odoo_project_id in repo_projects
                )
                project_modules.with_delay()._remap_to_specific_module()
            return False
        return module_branch
