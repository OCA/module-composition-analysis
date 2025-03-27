# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from urllib.parse import urljoin

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
    changelog_enabled_repository_ids = fields.One2many(
        comodel_name="odoo.project.repository",
        inverse_name="odoo_project_id",
        string="Enabled Repositories for CHANGELOG",
    )
    changelog_state = fields.Selection(
        selection=[
            ("none", "None"),
            ("in_progress", "In progress"),
            ("done", "Done"),
        ],
        default="none",
        copy=False,
    )
    changelog_url = fields.Char(compute="_compute_changelog_url")

    def _compute_changelog_url(self):
        for rec in self:
            rec.changelog_url = urljoin(
                rec.get_base_url() + "/",
                f"report/html/odoo_project_changelog.report_changelog/{rec.id}",
            )

    def action_generate_changelog(self):
        self.ensure_one()
        self.changelog_state = "in_progress"
        self.used_repository_ids.changelog = False
        jobs = self._create_jobs()
        chain(*jobs).delay()

    def action_open_changelog(self):
        return {
            "type": "ir.actions.act_url",
            "url": self.changelog_url,
            "target": "_new",
            "target_type": "public",
        }

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
        # Spawn job updating the CHANGELOG state to done
        delayable = self.delayable(
            description=(f"Set CHANGELOG as ready for {self.display_name}"),
            identity_key=identity_exact,
        )
        job = delayable._set_changelog_done()
        jobs.append(job)
        return jobs

    def _set_changelog_done(self):
        self.changelog_state = "done"
