# Copyright 2026 ACSONE SA/NV (<https://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

import git

from odoo import _, api, fields, models

from odoo.addons.queue_job.exception import RetryableJobError
from odoo.addons.queue_job.job import identity_exact

from ..lib.scanner import PinnedModuleScanner

_logger = logging.getLogger(__name__)


class OdooProjectModule(models.Model):
    _inherit = "odoo.project.module"

    source_repository_id = fields.Many2one(
        comodel_name="odoo.repository",
        string="Installed From",
        help=(
            "Fork the module is installed from, when it differs from the "
            "repository it belongs to. Its own 'Fork Of' tells where the "
            "module comes from, which is the only way to reach it for a module "
            "living in the fork alone."
        ),
    )
    source_clone_url = fields.Char(
        string="Source URL",
        help=(
            "Repository the module is installed from, as the dependency file "
            "spells it. Kept even when it matches no known repository, which "
            "is then the only trace of where the module comes from."
        ),
    )
    source_ref = fields.Char(
        string="Source Revision",
        help="Revision the module is frozen on: a commit, a tag or a PR ref.",
    )
    source_subdirectory = fields.Char(
        help="Path of the module within its source repository.",
    )
    is_pinned = fields.Boolean(
        compute="_compute_is_pinned",
        store=True,
        help="The module is frozen on a revision instead of a published version.",
    )
    analysed_ref = fields.Char(
        string="Analysed Revision",
        readonly=True,
        help=(
            "Revision the code of this module was last analysed at. A pinned "
            "revision never moves, so it is worth analysing once and never "
            "again."
        ),
    )

    @api.depends("source_clone_url", "source_ref")
    def _compute_is_pinned(self):
        for rec in self:
            rec.is_pinned = bool(rec.source_clone_url and rec.source_ref)

    @api.depends("version", "installed_version", "is_pinned")
    def _compute_to_upgrade(self):
        # Without an installed version the base computation falls back on the
        # upstream one, which reads as up to date. A module pinned on a
        # revision whose version could not be read is precisely the opposite:
        # nothing is known about it.
        res = super()._compute_to_upgrade()
        for rec in self:
            if rec.is_pinned and not rec.installed_version:
                rec.to_upgrade = True
        return res

    def action_analyse_pinned_revision(self):
        """Analyse the code of the pinned modules of this selection."""
        for rec in self.filtered("is_pinned"):
            rec._create_job_analyse_pinned_revision().delay()
        return True

    def _create_job_analyse_pinned_revision(self):
        """Return the job analysing this module at its pinned revision."""
        self.ensure_one()
        delayable = self.delayable(
            description=(
                f"Analyse {self.module_name} at {self.source_ref} "
                f"in {self.source_repository_id.display_name}"
            ),
            identity_key=identity_exact,
        )
        return delayable._analyse_pinned_revision()

    def _analyse_pinned_revision(self):
        """Analyse the code of this module at the revision it is pinned on.

        A pinned revision is the head of a pull request more often than of a
        branch, so no repository scan ever reaches it: neither the version of
        the module nor the analysis of its code can come from anywhere else.
        """
        self.ensure_one()
        repository = self.source_repository_id
        if not repository or not self.source_ref:
            return False
        module_branch = self.module_branch_id
        scanner = PinnedModuleScanner(
            branches=[], **repository._prepare_base_scanner_parameters()
        )
        try:
            data = scanner.scan_module_at_revision(
                module_branch.full_path, self.source_ref
            )
        except git.exc.GitError as exc:
            raise RetryableJobError(
                _("Cannot read %(module)s at %(ref)s in %(repository)s")
                % {
                    "module": module_branch.full_path,
                    "ref": self.source_ref,
                    "repository": repository.display_name,
                }
            ) from exc
        if data is None:
            _logger.warning(
                "%s: %s holds no %s at %s",
                self.display_name,
                repository.display_name,
                module_branch.full_path,
                self.source_ref,
            )
            return False
        values = {"analysed_ref": self.source_ref}
        version = (data.get("manifest") or {}).get("version")
        if version:
            values["installed_version"] = version
        self.sudo().write(values)
        # The module branch is shared with the repository the modules belong
        # to, whose scan is authoritative on it. Only one no scan ever reaches,
        # living in a pull request alone, takes its data from here.
        if not module_branch.last_scanned_commit:
            module_branch._update_from_pinned_revision(data)
        return True
