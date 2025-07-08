# Copyright 2025 Akretion
# Copyright 2025 Raphaël Reverdy <raphael.reverdy@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooProject(models.Model):
    _inherit = "odoo.project"

    module_branch_id_to_inject_mig = fields.Many2many(
        comodel_name="odoo.module.branch",
        relation="odoo_project_module_inj_rel",
        column1="odoo_project_id",
        column2="module_branch_id",
        string="Modules to inject",
    )

    module_branch_id_to_reject_mig = fields.Many2many(
        comodel_name="odoo.module.branch",
        relation="odoo_project_module_rej_rel",
        column1="odoo_project_id",
        column2="module_branch_id",
        string="Modules reject inject",
    )

    def _modules_to_migrate(self, migration_path_id):
        """Return the list of modules to migrate
        and inject (add) some module in the next version
        and reject (remove) some others.

        Goal is to support module rename accross version
        or bigger changes:
            like bank_payment(16) -> bank_payment_alternativa (18)
            like storage (14) -> fs_storage (18)
            like introduce new modules in new version
        """

        # start with the current module set
        base_modules_branch = self.project_module_ids.module_branch_id

        start_version = migration_path_id.source_branch_id
        end_version = migration_path_id.target_branch_id
        versions = start_version.search(
            [
                # sequence ordering is safe
                ["sequence", ">=", start_version.sequence],
                ["sequence", "<=", end_version.sequence],
                ["odoo_version", "=", True],
            ]
        )

        target_modules_branch = base_modules_branch.filtered(
            # exclude modules from previous or after versions
            lambda x, versions=versions: x.branch_id
            in versions
        )

        inject = {}
        reject = {}
        for version in versions:
            inject[version] = self.env["odoo.module.branch"].browse(False)
            reject[version] = self.env["odoo.module.branch"].browse(False)
        # TODO replace by recorset.grouped() in > 17.0 version

        # inject{ '16.0': [moduleA, moduleB], '17.0': ['moduleC'] }
        for module_branch_id in self.module_branch_id_to_inject_mig:
            inject[module_branch_id.branch_id] |= module_branch_id
        for module_branch_id in self.module_branch_id_to_reject_mig:
            reject[module_branch_id.branch_id] |= module_branch_id

        # now add and remove version per version
        # very naive algorithm
        for version in versions:
            for module_branch in inject[version]:
                # only add module_branch is module not already present
                if module_branch.module_id not in target_modules_branch.module_id:
                    target_modules_branch |= module_branch
            for module_branch in reject[version]:
                # only remove module_branch is module is present
                # we manage module_branch of different version of the same
                # module
                target_modules_branch = target_modules_branch.filtered(
                    lambda x, module_branch=module_branch: x.module_id
                    != module_branch.module_id
                )
        return target_modules_branch
