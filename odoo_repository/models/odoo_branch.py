# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class OdooBranch(models.Model):
    _name = "odoo.branch"
    _description = "Odoo Branch/Version"
    _order = "sequence, name"

    name = fields.Char(
        string="Version",
        required=True,
        index=True,
        help=(
            "An Odoo version is also used as an Odoo branch name in generic "
            "repositories (Odoo, OCA...)."
        ),
    )
    active = fields.Boolean(default=True)
    repository_branch_ids = fields.One2many(
        comodel_name="odoo.repository.branch",
        inverse_name="branch_id",
        string="Repositories",
        readonly=True,
    )
    sequence = fields.Integer()
    next_id = fields.Many2one(
        comodel_name="odoo.branch",
        compute="_compute_next_id",
    )

    _sql_constraints = [
        ("name_uniq", "UNIQUE (name)", "This branch already exists."),
    ]

    @api.constrains("name")
    def _constrains_name(self):
        odoo_version_pattern = r"^[0-9]+\.[0-9]$"
        for rec in self:
            version = re.search(odoo_version_pattern, rec.name)
            if not version:
                raise ValidationError(_("Version must match the pattern 'x.y'."))

    @api.depends("sequence")
    def _compute_next_id(self):
        for rec in self:
            rec.next_id = self.search(
                [("sequence", ">", rec.sequence)],
                order="sequence",
                limit=1,
            )

    @api.model
    def _recompute_sequence(self):
        """Recompute the 'sequence' field to get release branches sorted."""
        self.flush_recordset()
        odoo_versions_to_recompute = self._get_all_odoo_versions()
        for odoo_version in odoo_versions_to_recompute:
            query = """
                UPDATE odoo_branch
                SET sequence = (
                    SELECT pos.position
                    FROM (
                        SELECT
                            id,
                            row_number() OVER (
                                ORDER BY string_to_array(name, '.')::int[]
                            ) AS position
                        FROM odoo_branch
                    ) as pos
                    WHERE pos.id = %(id)s
                )
                WHERE id = %(id)s;
            """
            args = {
                "id": odoo_version.id,
            }
            self.env.cr.execute(query, args)
        self.invalidate_recordset(["sequence"])

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        res._recompute_sequence()
        return res

    def write(self, values):
        res = super().write(values)
        self._recompute_sequence()
        return res

    def action_scan(self, force=False):
        """Scan this branch in all repositories."""
        self.repository_branch_ids.action_scan(force=force)

    def action_force_scan(self):
        """Force the scan of this branch in all repositories.

        It will restart the scan without considering the last scanned commit,
        overriding already collected module data if any.
        """
        return self.action_scan(force=True)

    def _get_all_odoo_versions(self, active_test=False):
        """Return all Odoo versions, even archived ones."""
        return self.with_context(active_test=active_test).search([])
