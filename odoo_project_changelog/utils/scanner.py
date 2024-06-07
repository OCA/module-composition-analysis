# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.addons.odoo_repository.lib.scanner import ChangelogScanner


class ChangelogScannerOdooEnv(ChangelogScanner):
    """ChangelogScanner running on the same server than Odoo.

    This class takes an additional `env` parameter (`odoo.api.Environment`)
    used to request Odoo, and implement required methods to use it.
    """

    def __init__(self, *args, **kwargs):
        if kwargs.get("env"):
            self.env = kwargs.pop("env")
        super().__init__(*args, **kwargs)

    def _get_odoo_project_repository_data(self, project_repo_id):
        project_repo = (
            self.env["odoo.project.repository"].browse(project_repo_id).exists()
        )
        project = project_repo.odoo_project_id
        data = {
            "odoo_project_id": project.id,
            "branch": project.odoo_version_id.name,
            "source_commit": project_repo.deployed_commit,
            "target_commit": project_repo.target_commit,
            "modules": [
                # List of dicts {"id": PROJECT_MODULE_ID, ...}
                # {"id": 1, "name": "base", "path": "odoo/addons/base"},
                # {"id": 2, "name": "account", "path": "addons/account"},
                {"id": mod.id, "name": mod.module_name, "path": mod.full_path}
                for mod in project.project_module_ids.filtered_domain(
                    [
                        (
                            "repository_branch_id",
                            "=",
                            project_repo.repository_branch_id.id,
                        )
                    ]
                )
            ],
        }
        return data

    def _push_odoo_project_repository_changelog(self, project_repo_id, changelog):
        self.env["odoo.project.repository"].browse(
            project_repo_id
        ).exists().push_changelog(changelog)
