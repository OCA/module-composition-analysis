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

    def action_scan(self, branch_ids=None, force=False, raise_exc=True):
        for rec in self:
            # Scan only relevant branches regarding migration paths
            rec_ctx = rec
            if rec.specific:
                rec_ctx = rec.with_context(strict_branches_scan=True)
            super(OdooRepository, rec_ctx).action_scan(
                branch_ids=branch_ids, force=force, raise_exc=raise_exc
            )
        return True

    def _reset_scanned_commits(self, branch_ids=None):
        res = super()._reset_scanned_commits(branch_ids=branch_ids)
        if branch_ids is None:
            branch_ids = self.branch_ids.branch_id.ids
        repo_branches = self.branch_ids.filtered(
            lambda rb: rb.branch_id.id in branch_ids
        )
        repo_branches.module_ids.migration_ids.sudo().write(
            {
                "last_source_scanned_commit": False,
                "last_target_scanned_commit": False,
            }
        )
        return res

    def _create_subsequent_jobs(
        self, version_branch, next_versions_branches, all_versions_branches, data
    ):
        jobs = super()._create_subsequent_jobs(
            version_branch, next_versions_branches, all_versions_branches, data
        )
        # Prepare migration scan jobs when its the last repository scan
        last_scan = not next_versions_branches
        if not last_scan:
            return jobs
        # Check if the addons_paths are compatible with 'oca_port'
        disable_collect = self.env.context.get("disable_collect_migration_data")
        if not self.collect_migration_data or disable_collect:
            return jobs
        # Override to run the MigrationScanner once branches are scanned
        args = []
        if all_versions_branches:
            all_versions = [vb[0] for vb in all_versions_branches]
            # A strict scan of branches avoids unwanted migration scans
            # For instance if we are interested only by 14.0 and 17.0 branches,
            # this avoids to scan other migration paths like 15.0 -> 17.0
            # NOTE: a strict scan always occurs on specific repositories
            strict_scan = self.env.context.get("strict_branches_scan") or self.specific
            args = [
                "&" if strict_scan else "|",
                ("source_branch_id", "in", all_versions),
                ("target_branch_id", "in", all_versions),
            ]
        migration_paths = self.env["odoo.migration.path"].search(args)
        # Launch one job for all migration_paths
        if migration_paths:
            # Migration paths parameter containing the migration path ID +
            # the Odoo versions and branches to scan.
            # E.g. {MIG_PATH_ID: [('14.0', 'master'), ('18.0', '18.0-mig')], ...}
            migration_paths_param = {}
            for migration_path in migration_paths:
                source_rb = self.branch_ids.filtered(
                    lambda rb: rb.branch_id == migration_path.source_branch_id
                )
                target_rb = self.branch_ids.filtered(
                    lambda rb: rb.branch_id == migration_path.target_branch_id
                )
                # Need the two Odoo versions of the migration path available
                # in the scanned repository
                if not source_rb or not target_rb:
                    continue
                # Build list of tuples (Odoo version, branch name) corresponding
                # to the migration path
                versions_branches = [
                    (
                        source_rb.branch_id.name,
                        source_rb.cloned_branch or source_rb.branch_id.name,
                    ),
                    (
                        target_rb.branch_id.name,
                        target_rb.cloned_branch or target_rb.branch_id.name,
                    ),
                ]
                migration_paths_param[migration_path.id] = versions_branches

            delayable = self.delayable(
                description=f"Collect {self.display_name} migration data",
                identity_key=identity_exact,
            )
            job = delayable._scan_migration_paths(migration_paths_param)
            jobs.append(job)
        return jobs

    def _scan_migration_paths(self, migration_paths_param):
        """Scan repository branches to collect modules migration data.

        Spawn one job per module to scan.
        """
        self.ensure_one()
        jobs = []
        for migration_path_id in migration_paths_param:
            versions_branches = migration_paths_param[migration_path_id]
            migration_path = (
                self.env["odoo.migration.path"]
                .browse(
                    # Job encodes dict key as string => convert it to integer
                    int(migration_path_id)
                )
                .exists()
            )
            if not migration_path:
                continue
            modules_to_scan = self._migration_get_modules_to_scan(migration_path)
            if modules_to_scan:
                jobs.extend(
                    self._migration_create_jobs_scan_module(
                        migration_path, versions_branches, modules_to_scan
                    )
                )
        if jobs:
            chain(*jobs).delay()
        return True

    def _migration_create_jobs_scan_module(
        self, migration_path, versions_branches, modules_to_scan
    ):
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
                migration_path.id, versions_branches, module.id
            )
            jobs.append(job)
        return jobs

    def _scan_migration_module(
        self, migration_path_id, versions_branches, module_branch_id
    ):
        """Scan migration path for `module_branch_id`.

        The migration scan can only occur if:
            - target module doesn't exist (and can be migrated)
            - source and target modules share the same commits histories (able to
              collect migration data)

        Also, a target module could have been renamed while sharing the commits history.

        But a module that has been replaced (different name, different commits
        history, but providing the same feature) in next versions cannot be scanned.
        Such module will get a migration status "Replaced".
        """
        module = self.env["odoo.module.branch"].browse(module_branch_id).exists()
        module.ensure_one()
        migration_path = (
            self.env["odoo.migration.path"].browse(migration_path_id).exists()
        )
        # Skip migration scan if module is replaced in next versions
        if module._replaced_by_module_in_target_version(
            migration_path.target_branch_id
        ):
            return (
                f"{module.name} is now replaced by "
                f"{module.next_odoo_version_module_id.name}, no need to collect "
                "migration data."
            )
        # Check if module has already been migrated on target version but in a
        # different repository. If so, tune the scanner parameters to perform
        # the scan from current repo to new one.
        target_repository = None
        mig = module.migration_ids.filtered(
            lambda mig: mig.migration_path_id.id == migration_path_id
        )
        target_module = mig.target_module_branch_id
        if target_module.repository_branch_id:
            target_repository = target_module.repository_id
            if not target_repository.collect_migration_data:
                return (
                    "Cannot collect migration data on repository "
                    f"{target_repository.display_name}."
                )
        params = self._prepare_migration_scanner_parameters(
            versions_branches, target_repository
        )
        module_names = [module.module_id.name]
        if target_module:
            if module.module_id != target_module.module_id:
                module_names = [(module.module_id.name, target_module.module_id.name)]
        # Run the migration scan
        try:
            scanner = MigrationScannerOdooEnv(**params)
            return scanner.scan(
                addons_path=module.addons_path,
                target_addons_path=target_module.addons_path or module.addons_path,
                module_names=module_names,
            )
        except Exception as exc:
            raise RetryableJobError("Scanner error") from exc

    def _migration_get_modules_to_scan(self, migration_path):
        """Return `odoo.module.branch` records that need a migration scan."""
        self.ensure_one()
        mb_model = self.env["odoo.module.branch"]
        modules = mb_model.search(
            [
                (
                    "repository_id",
                    "=",
                    self.id,
                ),
                ("branch_id", "=", migration_path.source_branch_id.id),
                ("migration_scan", "=", True),
            ]
        )
        module_ids = []
        for module in modules:
            migration = module.migration_ids.filtered(
                lambda mig: mig.migration_path_id == migration_path
            )
            if migration and not migration.migration_scan:
                # Skip module that do not need a scan for the given migration path
                continue
            module_ids.append(module.id)
        return mb_model.browse(module_ids)

    def _prepare_migration_scanner_parameters(
        self, migration_path, target_repository=None
    ):
        ir_config = self.env["ir.config_parameter"]
        repositories_path = ir_config.sudo().get_param(self._repositories_path_key)
        params = {
            "org": self.org_id.name,
            "name": self.name,
            "clone_url": self.clone_url,
            "migration_path": migration_path,
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
        if target_repository and target_repository != self:
            params["new_repo_name"] = target_repository.name
            params["new_repo_url"] = target_repository.clone_url
        return params

    def _pre_create_or_update_module_branch(self, rec, values, raw_data):
        # Handle migration data
        values = super()._pre_create_or_update_module_branch(rec, values, raw_data)
        mig_model = self.env["odoo.module.branch.migration"]
        migrations = raw_data.get("migrations", [])
        values["migration_ids"] = []
        for mig in migrations:
            source_branch = self.env["odoo.branch"].search(
                [("name", "=", mig["source_branch"])]
            )
            target_branch = self.env["odoo.branch"].search(
                [("name", "=", mig["target_branch"])]
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
