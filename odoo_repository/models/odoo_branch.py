# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class OdooBranch(models.Model):
    _name = "odoo.branch"
    _description = "Odoo Branch"
    _order = "sequence, name"

    name = fields.Char(required=True, index=True)
    odoo_version = fields.Boolean(default=True)
    active = fields.Boolean(default=True)
    repository_branch_ids = fields.One2many(
        comodel_name="odoo.repository.branch",
        inverse_name="branch_id",
        string="Repositories",
        readonly=True,
    )
    sequence = fields.Integer()

    _sql_constraints = [
        ("name_uniq", "UNIQUE (name)", "This branch already exists."),
    ]

    def _recompute_sequence(self):
        """Recompute the 'sequence' field to get release branches sorted."""
        self.flush_recordset()
        odoo_versions_to_recompute = self.search([("odoo_version", "=", True)])
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
                        WHERE odoo_version = true
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
