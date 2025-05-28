# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import base64
import csv
import io

from odoo import api, fields, models


class OdooProjectExportMigrationReport(models.TransientModel):
    _name = "odoo.project.export.migration.report"
    _description = "Export a migration report for an Odoo project"

    odoo_project_id = fields.Many2one(
        comodel_name="odoo.project",
        string="Project",
        required=True,
    )
    odoo_version_id = fields.Many2one(related="odoo_project_id.odoo_version_id")
    available_migration_path_ids = fields.One2many(
        comodel_name="odoo.migration.path",
        compute="_compute_available_migration_path_ids",
        string="Available Migration Paths",
    )
    migration_path_id = fields.Many2one(
        comodel_name="odoo.migration.path",
        string="Migration Path",
        required=True,
    )

    @api.depends("odoo_project_id")
    def _compute_available_migration_path_ids(self):
        for rec in self:
            rec.available_migration_path_ids = (
                rec.odoo_project_id.module_migration_ids.migration_path_id
            )

    def action_export_report(self):
        """Export a migration report in CSV format."""
        self.ensure_one()
        migration_path_str = (
            f"{self.migration_path_id.source_branch_id.name}_"
            f"{self.migration_path_id.target_branch_id.name}"
        )
        now_str = fields.Datetime.now().strftime("%Y%m%d-%Hh%M")
        content = self._get_csv_content()
        values = {
            "res_model": self.odoo_project_id._name,
            "res_id": self.odoo_project_id.id,
            "name": (
                f"{self.odoo_project_id.display_name}_"
                f"{migration_path_str}_{now_str}.csv"
            ),
            "type": "binary",
            "datas": base64.b64encode(content.encode()),
        }
        attachment = self.env["ir.attachment"].create(values)
        # self.odoo_project_id.attachment_ids |= attachment
        attachment_url = (
            f"web/content/?model=ir.attachment&id={attachment.id}"
            "&filename_field=name&field=datas&download=true"
            f"&name={attachment.name}"
        )
        action = {"type": "ir.actions.act_url", "url": attachment_url, "target": "self"}
        return action

    def _get_csv_content(self):
        with io.StringIO() as csvfile:
            header = self._get_csv_header()
            writer = csv.DictWriter(csvfile, fieldnames=header)
            writer.writeheader()
            for line in self._get_csv_lines():
                writer.writerow(line)
            csvfile.seek(0)
            return csvfile.getvalue()

    def _get_csv_lines(self):
        # org_model = self.env["odoo.repository.org"]
        project_module_mig_model = self.env["odoo.project.module.migration"]
        repo_model = self.env["odoo.repository"]
        group_by_repo = project_module_mig_model.read_group(
            [
                ("odoo_project_id", "=", self.odoo_project_id.id),
                ("migration_path_id", "=", self.migration_path_id.id),
            ],
            ["repository_id"],
            ["repository_id"],
        )
        for group_repo in group_by_repo:
            # Put the repository on its own line
            if group_repo["repository_id"]:
                repo_id = group_repo["repository_id"][0]
                repo = repo_model.browse(repo_id)
                yield {"Repository": repo.display_name}
            else:
                yield {"Repository": "Unknown"}
            domain_with_repo = group_repo["__domain"]
            modules = project_module_mig_model.search(domain_with_repo)
            for module in modules:
                yield self._prepare_csv_module_line(module)

    def _get_csv_header(self):
        return [
            "Repository",
            "Module",
            "Dependencies",
            "Global Dep. Level",
            "Non-Std Dep. Level",
            "Python",
            "XML",
            "JavaScript",
            "CSS",
            "Status",
            "Info",
            "Warning",
        ]

    def _prepare_csv_module_line(self, module):
        line = {
            "Module": module.module_name,
            "Dependencies": "\n".join(module.dependency_ids.mapped("module_name")),
            "Global Dep. Level": module.global_dependency_level,
            "Non-Std Dep. Level": module.non_std_dependency_level,
            "Python": module.sloc_python,
            "XML": module.sloc_xml,
            "JavaScript": module.sloc_js,
            "CSS": module.sloc_css,
            "Status": module.state,
            "Info": self._get_csv_module_info(module),
            "Warning": self._get_csv_module_warning(module),
        }
        return line

    def _get_csv_module_info(self, module):
        migration = module.module_migration_id
        info = []
        # Module renamed or replaced by another one
        if migration.renamed_to_module_id:
            info.append(f"Renamed to {migration.target_module_branch_id.module_name}")
        elif migration.replaced_by_module_id:
            info.append(
                f"Replaced by {migration.target_module_branch_id.module_name} "
                f"(in {migration.target_module_branch_id.repository_id.display_name})"
            )
        # Migration to review or commits/PRs to port
        if migration.state == "review_migration":
            if migration.pr_url:
                info.append(f"PR to review: {migration.pr_url}")
        elif migration.process == "port_commits":
            nb_prs = len(migration.results)
            msg = f"{nb_prs} PR(s) to check/port"
            msg = "\n".join(
                [msg] + [f"- {pr['url']}" for pr in migration.results.values()]
            )
            info.append(msg)
        # Migration scripts
        if module.migration_script_ids:
            nb_scripts = len(module.migration_script_ids)
            info_mig = f"\n\n{nb_scripts} migration script(s) to consider:"
            info_mig = "\n".join(
                [info_mig]
                + [f"- {sc.migration_script_url}" for sc in module.migration_script_ids]
            )
            info.append(info_mig)
        return "\n\n".join(info)

    def _get_csv_module_warning(self, module):
        warning = ""
        if not module.repository_id or module.pr_url:
            warning = f"Not merged in {module.branch_id.name} yet"
        return warning
