# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models

from odoo.addons.queue_job.job import identity_exact

from ..utils.scanner import MigrationScannerOdooEnv


class OdooRepository(models.Model):
    _inherit = "odoo.repository"

    collect_migration_data = fields.Boolean(
        string="Collect migration data",
        help=(
            "Collect migration data based on the configured migration paths."
        ),
        default=False,
    )

    def _reset_scanned_commits(self):
        res = super()._reset_scanned_commits()
        self.branch_ids.module_ids.migration_ids.sudo().write(
            {
                "last_source_scanned_commit": False,
                "last_target_scanned_commit": False,
            }
        )
        return res

    def _create_jobs(self, branches):
        jobs = super()._create_jobs(branches)
        # Check if the addons_paths are compatible with 'oca_port'
        if not self.collect_migration_data:
            return jobs
        # Override to run the MigrationScanner once all branches are scanned
        migration_paths = self.env["odoo.migration.path"].search([])
        for rec in migration_paths:
            migration_path = (
                rec.source_branch_id.name,
                rec.target_branch_id.name
            )
            delayable = self.delayable(
                description=(
                    f"Collect {self.display_name} "
                    f"{' > '.join(migration_path)} migration data"
                ),
                identity_key=identity_exact
            )
            job = delayable._scan_migration_data(migration_path)
            jobs.append(job)
        return jobs

    def _scan_migration_data(self, migration_path):
        """Scan repository branches to collect modules migration data."""
        params = self._prepare_migration_scanner_parameters(migration_path)
        scanner = MigrationScannerOdooEnv(**params)
        return scanner.scan()

    def _prepare_migration_scanner_parameters(self, migration_path):
        key = self._repositories_path_key
        repositories_path = self.env["ir.config_parameter"].get_param(key)
        return {
            "org": self.org_id.name,
            "name": self.name,
            "clone_url": self.clone_url,
            "migration_paths": [migration_path],
            "repositories_path": repositories_path,
            "env": self.env
        }
