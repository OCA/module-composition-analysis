# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class OdooRepositoryBranch(models.Model):
    _name = "odoo.repository.branch"
    _description = "Odoo Modules Repository Branch"

    name = fields.Char(compute="_compute_name", store=True, index=True)
    repository_id = fields.Many2one(
        comodel_name="odoo.repository",
        ondelete="cascade",
        string="Repository",
        required=True,
        index=True,
        readonly=True,
    )
    branch_id = fields.Many2one(
        comodel_name="odoo.branch",
        ondelete="cascade",
        string="Branch",
        required=True,
        index=True,
        readonly=True,
    )
    module_ids = fields.One2many(
        comodel_name="odoo.module.branch",
        inverse_name="repository_branch_id",
        string="Modules",
        readonly=True,
    )
    last_scanned_commit = fields.Char(readonly=True)
    active = fields.Boolean(compute="_compute_active", store=True)

    _sql_constraints = [
        (
            "repository_id_branch_id_uniq",
            "UNIQUE (repository_id, branch_id)",
            "This branch already exists for this repository.",
        ),
    ]

    @api.depends("repository_id.display_name", "branch_id.name")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.repository_id.display_name}#{rec.branch_id.name}"

    @api.depends("repository_id.active", "branch_id.active")
    def _compute_active(self):
        for rec in self:
            rec.active = all((rec.repository_id.active, rec.branch_id.active))

    def action_scan(self, force=False):
        """Scan the repository/branch."""
        return self.repository_id.action_scan(
            branches=[self.branch_id.name], force=force
        )

    def action_force_scan(self):
        """Force the scan of the repository/branch.

        It will restart the scan without considering the last scanned commit,
        overriding already collected module data if any.
        """
        return self.action_scan(force=True)

    def _to_dict(self):
        """Convert branch repository data to a dictionary."""
        self.ensure_one()
        return {
            "org": self.repository_id.org_id.name,
            "name": self.repository_id.name,
            "repo_url": self.repository_id.repo_url,
            "repo_type": self.repository_id.repo_type,
            "active": self.repository_id.active,
            "branch": self.branch_id.name,
            "last_scanned_commit": self.last_scanned_commit,
        }
