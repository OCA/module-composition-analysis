# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models

from ..utils.scanner import ChangelogScannerOdooEnv


class OdooProjectRepository(models.Model):
    _name = "odoo.project.repository"
    _description = "Repository used in a project"

    odoo_project_id = fields.Many2one(
        comodel_name="odoo.project",
        ondelete="cascade",
        string="Project",
        required=True,
        index=True,
        readonly=True,
    )
    repository_branch_id = fields.Many2one(
        comodel_name="odoo.repository.branch",
        ondelete="cascade",
        string="Repository Branch",
        required=True,
        index=True,
    )
    deployed_commit = fields.Char(help="The changelog is generated from this commit.")
    target_commit = fields.Char(
        help=(
            "Changelog is generated until this commit. "
            "If not set, the latest commit of the branch is used."
        )
    )
    active = fields.Boolean(string="Include", default=True)
    changelog = fields.Serialized()

    def _prepare_changelog_scanner_parameters(self):
        ir_config = self.env["ir.config_parameter"]
        odoo_repository = self.repository_branch_id.repository_id
        repositories_path = ir_config.get_param(odoo_repository._repositories_path_key)
        return {
            "org": odoo_repository.org_id.name,
            "name": odoo_repository.name,
            "clone_url": odoo_repository.clone_url,
            "odoo_project_repository_id": self.id,
            "repositories_path": repositories_path,
            "repo_type": odoo_repository.repo_type,
            "ssh_key": odoo_repository.ssh_key_id.private_key,
            "token": odoo_repository._get_token(),
            "env": self.env,
        }

    def _generate_changelog(self):
        self.ensure_one()
        params = self._prepare_changelog_scanner_parameters()
        scanner = ChangelogScannerOdooEnv(**params)
        scanner.scan()

    def push_changelog(self, changelog):
        """Store the changelog. Called by the scanner."""
        self.ensure_one()
        self.changelog = changelog
        self.target_commit = self.changelog["target_commit"]

    def _get_report_data(self):
        """Return data used by the CHANGELOG report."""
        self.ensure_one()
        project_module_model = self.env["odoo.project.module"]
        if not self.changelog.get("modules"):
            return {"categories": {}, "count": 0}
        # Collect all related categories and sort them by name
        project_module_ids = [
            int(project_module_id) for project_module_id in self.changelog["modules"]
        ]
        project_modules = project_module_model.browse(project_module_ids).exists()
        categories = project_modules.category_id.sorted(
            key=lambda o: (o.name or "").lower()  # Case insensitive
        )
        data = {"categories": {categ: {} for categ in categories}}
        data["categories"][self.env["odoo.module.category"]] = {}
        data["count"] = len(self.changelog["modules"])
        for project_module_id, module_data in self.changelog["modules"].items():
            project_module = project_module_model.browse(int(project_module_id))
            categ = project_module.category_id
            data["categories"][categ][project_module] = module_data
        return data
