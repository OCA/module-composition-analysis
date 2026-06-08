# Copyright 2026  Akretion (https://www.akretion.com).
# @author Sébastien Alix <sebastien.alix@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, fields, models


class OdooModuleBranchTimeline(models.Model):
    _inherit = "odoo.module.branch.timeline"

    project_migration_ids = fields.Many2many(
        comodel_name="odoo.project.module.migration",
        string="Project Migrations",
        compute="_compute_project_migration_ids",
    )

    @api.depends("module_branch_id", "next_module_id", "odoo_version_id")
    def _compute_project_migration_ids(self):
        for rec in self:
            impacted_modules = rec._get_all_impacted_modules()
            rec.project_migration_ids = (
                self.env["odoo.project.module.migration"]
                .search(
                    [
                        (
                            "migration_path_id.target_branch_id.sequence",
                            ">=",
                            rec.odoo_version_id.sequence,
                        ),
                        "|",
                        "|",
                        ("module_id", "in", impacted_modules.ids),
                        ("renamed_to_module_id", "in", impacted_modules.ids),
                        ("replaced_by_module_id", "in", impacted_modules.ids),
                    ]
                )
                .sudo()
            )

    # Update relevant project migration records on timeline update.
    #
    # When a module is renamed or replaced, we refresh all impacted project
    # migration data records as done in 'odoo_repository_migration' module for
    # 'odoo.module.branch.migration' records.
    #
    # E.g.
    #     if a module on 17.0 is set as renamed starting from 18.0, existing
    #     project migration data (17.0 -> 18.0, or 17.0 -> 19.0) will be aware
    #     of such change even if migration data are not collected on source
    #     repository.

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.project_migration_ids.force_update()
        return records

    @api.model
    def write(self, vals):
        project_migrations = self.project_migration_ids
        res = super().write(vals)
        (self.project_migration_ids | project_migrations).force_update()
        return res

    def unlink(self):
        project_migrations = self.project_migration_ids
        res = super().unlink()
        project_migrations.force_update()
        return res

    def open_project_migrations(self):
        self.ensure_one()
        xml_id = "odoo_project_migration.odoo_project_module_migration_action"
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        action["name"] = _("Project Migrations")
        action["domain"] = [("id", "in", self.project_migration_ids.ids)]
        return action
