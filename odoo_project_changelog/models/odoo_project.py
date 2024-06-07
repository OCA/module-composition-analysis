# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models

from odoo.addons.queue_job.delay import chain
from odoo.addons.queue_job.job import identity_exact


class OdooProject(models.Model):
    _inherit = "odoo.project"

    used_repository_ids = fields.One2many(
        comodel_name="odoo.project.repository",
        inverse_name="odoo_project_id",
        string="Used Repositories",
        context={"active_test": False},
    )

    def action_generate_changelog(self):
        self.ensure_one()
        jobs = self._create_jobs()
        chain(*jobs).delay()

    def _create_jobs(self):
        self.ensure_one()
        jobs = []
        # Spawn jobs generating a changelog for each repository
        for repo in self.used_repository_ids:
            if not repo.active:
                continue
            delayable = repo.delayable(
                description=(
                    f"Collect CHANGELOG data for {self.display_name}, "
                    f"repository {repo.repository_branch_id.display_name}"
                ),
                identity_key=identity_exact,
            )
            job = delayable._generate_changelog()
            jobs.append(job)
        # Spawn job consolidating all changelogs within a report
        delayable = self.delayable(
            description=(f"Generate CHANGELOG report for {self.display_name}"),
            identity_key=identity_exact,
        )
        job = delayable._generate_changelog_report()
        jobs.append(job)
        return jobs

    def _generate_changelog_report(self):
        raise NotImplementedError
