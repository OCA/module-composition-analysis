# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models, tools

from odoo.addons.queue_job.delay import chain
from odoo.addons.queue_job.exception import RetryableJobError
from odoo.addons.queue_job.job import identity_exact

from ..utils.scanner import MigrationScannerOdooEnv


class OdooRepository(models.Model):
    _inherit = "odoo.repository"

    collect_migration_data = fields.Boolean(
        string="Collect migration data",
        help=("Collect migration data based on the configured migration paths."),
        default=False,
    )

    def _reset_scanned_commits(self, branches=None):
        res = super()._reset_scanned_commits(branches)
        if branches is None:
            branches = []
        branches_ = (
            self.branch_ids.filtered(lambda br: br.branch_id.name in branches)
            if branches
            else self.branch_ids
        )
        branches_.module_ids.migration_ids.sudo().write(
            {
                "last_source_scanned_commit": False,
                "last_target_scanned_commit": False,
            }
        )
        return res

    def _create_subsequent_jobs(self, branch, next_branches, all_branches, data):
        jobs = super()._create_subsequent_jobs(
            branch, next_branches, all_branches, data
        )
        # Prepare migration scan jobs when its the last repository scan
        last_scan = not next_branches
        if not last_scan:
            return jobs
        # Check if the addons_paths are compatible with 'oca_port'
        disable_collect = self.env.context.get("disable_collect_migration_data")
        if not self.collect_migration_data or disable_collect:
            return jobs
        # Override to run the MigrationScanner once branches are scanned
        args = []
        if all_branches:
            # A strict scan of branches avoids unwanted migration scans
            # For instance if we are interested only by 14.0 and 17.0 branches,
            # this avoids to scan other migration paths like 15.0 -> 17.0
            strict_scan = self.env.context.get("strict_branches_scan")
            args = [
                "&" if strict_scan else "|",
                ("source_branch_id", "in", all_branches),
                ("target_branch_id", "in", all_branches),
            ]
        migration_paths = self.env["odoo.migration.path"].search(args)
        # Launch one job for all migration_paths
        if migration_paths:
            delayable = self.delayable(
                description=f"Collect {self.display_name} migration data",
                identity_key=identity_exact,
            )
            job = delayable._scan_migration_paths(migration_paths.ids)
            jobs.append(job)
        return jobs

    def _scan_migration_paths(self, migration_path_ids):
        """Scan repository branches to collect modules migration data.

        Spawn one job per module to scan.
        """
        self.ensure_one()
        jobs = []
        migration_paths = (
            self.env["odoo.migration.path"].browse(migration_path_ids).exists()
        )
        for migration_path in migration_paths:
            modules_to_scan = self._migration_get_modules_to_scan(migration_path)
            if modules_to_scan:
                jobs.extend(
                    self._migration_create_jobs_scan_module(
                        migration_path, modules_to_scan
                    )
                )
        if jobs:
            chain(*jobs).delay()
        return True

    def _migration_create_jobs_scan_module(self, migration_path, modules_to_scan):
        jobs = []
        mig_path = (
            migration_path.source_branch_id.name,
            migration_path.target_branch_id.name,
        )
        for module in modules_to_scan:
            delayable = self.delayable(
                description=(
                    f"Collect {module.name} migration data " f"({' > '.join(mig_path)})"
                ),
                identity_key=identity_exact,
            )
            job = delayable._scan_migration_module(
                migration_path.id, module.module_id.name
            )
            jobs.append(job)
        return jobs

    def _scan_migration_module(self, migration_path_id, module_name):
        """Scan migration path for `module_name`."""
        migration_path = (
            self.env["odoo.migration.path"].browse(migration_path_id).exists()
        )
        params = self._prepare_migration_scanner_parameters(migration_path)
        try:
            scanner = MigrationScannerOdooEnv(**params)
            return scanner.scan(modules=[module_name])
        except Exception as exc:
            raise RetryableJobError("Scanner error") from exc

    def _migration_get_modules_to_scan(self, migration_path):
        """Return `odoo.module.branch` records that need a migration scan."""
        self.ensure_one()
        return self.env["odoo.module.branch"].search(
            [
                (
                    "repository_id",
                    "=",
                    self.id,
                ),
                ("branch_id", "=", migration_path.source_branch_id.id),
                ("migration_scan", "=", True),
                # Do not scan removed or pending (in PR) modules
                ("removed", "=", False),
                ("last_scanned_commit", "!=", False),
            ]
        )

    def _prepare_migration_scanner_parameters(self, migration_path):
        ir_config = self.env["ir.config_parameter"]
        repositories_path = ir_config.get_param(self._repositories_path_key)
        mig_path = (
            migration_path.source_branch_id.name,
            migration_path.target_branch_id.name,
        )
        return {
            "org": self.org_id.name,
            "name": self.name,
            "clone_url": self.clone_url,
            "migration_path": mig_path,
            "repositories_path": repositories_path,
            "repo_type": self.repo_type,
            "ssh_key": self.ssh_key_id.private_key,
            "token": self._get_token(),
            "workaround_fs_errors": (
                self.env.company.config_odoo_repository_workaround_fs_errors
            ),
            "clone_name": self.clone_name,
            "env": self.env,
        }

    def _pre_create_or_update_module_branch(self, rec, values, raw_data):
        # Handle migration data
        values = super()._pre_create_or_update_module_branch(rec, values, raw_data)
        mig_model = self.env["odoo.module.branch.migration"]
        migrations = raw_data.get("migrations", [])
        values["migration_ids"] = []
        for mig in migrations:
            source_branch = self.env["odoo.branch"].search(
                [("odoo_version", "=", True), ("name", "=", mig["source_branch"])]
            )
            target_branch = self.env["odoo.branch"].search(
                [("odoo_version", "=", True), ("name", "=", mig["target_branch"])]
            )
            if not source_branch or not target_branch:
                # Such branches are not configured on this instance, skip
                continue
            migration_path = self._get_migration_path(
                source_branch.id, target_branch.id
            )
            mig_values = {
                "migration_path_id": migration_path.id,
                "process": mig["process"],
                "results": mig["results"],
                "last_source_scanned_commit": mig["last_source_scanned_commit"],
                "last_target_scanned_commit": mig["last_target_scanned_commit"],
            }
            # Check if this migration data exists to update it, otherwise create it
            mig_rec = None
            if rec:
                mig_rec = mig_model.search(
                    [
                        ("migration_path_id", "=", migration_path.id),
                        ("module_branch_id", "=", rec.id),
                    ],
                )
            if mig_rec:
                mig_values_ = fields.Command.update(mig_rec.id, mig_values)
            else:
                mig_values_ = fields.Command.create(mig_values)
            values["migration_ids"].append(mig_values_)
        return values

    @tools.ormcache("source_branch_id", "target_branch_id")
    def _get_migration_path(self, source_branch_id, target_branch_id):
        rec = self.env["odoo.migration.path"].search(
            [
                ("source_branch_id", "=", source_branch_id),
                ("target_branch_id", "=", target_branch_id),
            ],
            limit=1,
        )
        values = {
            "source_branch_id": source_branch_id,
            "target_branch_id": target_branch_id,
        }
        if not rec:
            rec = self.env["odoo.migration.path"].sudo().create(values)
        return rec
