# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooBranch(models.Model):
    _name = "odoo.branch"
    _description = "Odoo Branch"
    _order = "name"

    name = fields.Char(required=True, index=True)
    odoo_version = fields.Boolean(default=True)
    active = fields.Boolean(default=True)
    repository_branch_ids = fields.One2many(
        comodel_name="odoo.repository.branch",
        inverse_name="branch_id",
        string="Repositories",
        readonly=True,
    )

    _sql_constraints = [
        ("name_uniq", "UNIQUE (name)", "This branch already exists."),
    ]

    def action_scan(self, force=False):
        """Scan this branch in all repositories."""
        self.repository_branch_ids.action_scan(force=force)

    def action_force_scan(self):
        """Force the scan of this branch in all repositories.

        It will restart the scan without considering the last scanned commit,
        overriding already collected module data if any.
        """
        return self.action_scan(force=True)
