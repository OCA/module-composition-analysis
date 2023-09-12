# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, fields, models


class OdooProjectGenerateMigrationData(models.TransientModel):
    _name = "odoo.project.generate.migration.data"
    _description = "Generate migration data for an Odoo project"

    odoo_project_id = fields.Many2one(
        comodel_name="odoo.project",
        string="Project",
        required=True,
    )
    odoo_version_id = fields.Many2one(related="odoo_project_id.odoo_version_id")
    migration_path_id = fields.Many2one(
        comodel_name="odoo.migration.path",
        string="Migration Path",
        required=True,
    )

    def action_generate_data(self):
        """Generate migration data for the given Odoo project."""
        self.ensure_one()
        module_migration_model = self.env["odoo.project.module.migration"]
        module_migrations_to_unlink = module_migration_model.search(
            [
                ("odoo_project_id", "=", self.odoo_project_id.id),
                ("migration_path_id", "=", self.migration_path_id.id),
            ]
        )
        module_migrations_to_unlink.sudo().unlink()
        values_list = []
        for module_branch in self.odoo_project_id.module_branch_ids:
            values = self._prepare_module_migration_values(module_branch)
            values_list.append(values)
        module_migration_model.sudo().create(values_list)
        # Open the generated migration data
        action = self.odoo_project_id.open_migration_data()
        action["domain"].append(
            ("migration_path_id", "=", self.migration_path_id.id)
        )
        action["display_name"] = _("Migration") + f" {self.migration_path_id.name}"
        return action

    def _prepare_module_migration_values(self, module_branch):
        return {
            "odoo_project_id": self.odoo_project_id.id,
            "migration_path_id": self.migration_path_id.id,
            "source_module_branch_id": module_branch.id,
        }
