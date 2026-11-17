# Copyright 2026 ACSONE SA/NV (<https://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models


class OdooRepository(models.Model):
    _inherit = "odoo.repository"

    def _create_subsequent_jobs(
        self, version_branch, next_versions_branches, all_versions_branches, data
    ):
        # Appending the resolution to the chain of the scan jobs is what makes
        # it read an up to date dependency file: the branch has just been
        # fetched by the job detecting the modules to scan. It also runs after
        # the modules have been scanned, so the dependency graph it walks to
        # complete the application modules is the fresh one.
        jobs = super()._create_subsequent_jobs(
            version_branch, next_versions_branches, all_versions_branches, data
        )
        if not data:
            # The branch does not exist, there is nothing to read
            return jobs
        version, __ = version_branch
        for project in self._get_projects_to_resolve(version):
            jobs.append(
                project._create_job_resolve_dependencies(scan_repositories=True)
            )
        return jobs

    def _get_projects_to_resolve(self, version):
        """Return the projects whose dependency file this repository holds."""
        self.ensure_one()
        return self.env["odoo.project"].search(
            [
                ("dependency_management", "=", "resolved"),
                ("odoo_version_id.name", "=", version),
                ("repository_id", "=", self.id),
            ]
        )
