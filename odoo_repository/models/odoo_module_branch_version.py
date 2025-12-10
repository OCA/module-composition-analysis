# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class OdooModuleBranchVersion(models.Model):
    _name = "odoo.module.branch.version"
    _description = "Version of a Odoo Module on a given branch"
    _order = "branch_sequence DESC, sequence DESC"

    module_branch_id = fields.Many2one(
        comodel_name="odoo.module.branch",
        ondelete="cascade",
        string="Module",
        required=True,
        index=True,
    )
    branch_id = fields.Many2one(
        related="module_branch_id.branch_id",
        store=True,
    )
    module_id = fields.Many2one(
        string="Module",
        related="module_branch_id.module_id",
        store=True,
        index=True,
    )
    module_name = fields.Char(
        string="Module Technical Name",
        related="module_branch_id.module_name",
        store=True,
        index=True,
    )
    branch_sequence = fields.Integer(
        string="Branch Sequence",
        related="branch_id.sequence",
        store=True,
    )
    name = fields.Char(required=True)
    manifest_value = fields.Char(
        required=True, help="Technical field to host the manifest value."
    )
    commit = fields.Char()
    has_migration_script = fields.Boolean(default=False)
    migration_script_url = fields.Char(
        string="Migration Script",
        compute="_compute_migration_script_url",
    )
    sequence = fields.Integer()

    _sql_constraints = [
        (
            "module_branch_id_name_manifest_value_uniq",
            "UNIQUE (module_branch_id, name, manifest_value)",
            "This version already exists for this module.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        res._recompute_sequence()
        return res

    def write(self, values):
        res = super().write(values)
        self._recompute_sequence()
        return res

    def _recompute_sequence(self):
        """Recompute the 'sequence' field to get versions sorted."""
        self.flush_recordset()
        versions_to_recompute = self.search(
            [("module_branch_id", "in", self.module_branch_id.ids)]
        )
        for version in versions_to_recompute:
            query = """
                UPDATE odoo_module_branch_version
                SET sequence = (
                    SELECT pos.position
                    FROM (
                        SELECT
                            id,
                            row_number() OVER (
                                ORDER BY string_to_array(name, '.')::int[]
                            ) AS position
                        FROM odoo_module_branch_version
                        WHERE module_branch_id = %(module_branch_id)s
                    ) as pos
                    WHERE pos.id = %(id)s
                )
                WHERE id = %(id)s;
            """
            args = {
                "module_branch_id": version.module_branch_id.id,
                "id": version.id,
            }
            self.env.cr.execute(query, args)
        self.invalidate_recordset(["sequence"])

    @api.depends("name", "has_migration_script")
    def _compute_migration_script_url(self):
        for rec in self:
            rec.migration_script_url = False
            repo = rec.module_branch_id.repository_id
            if rec.has_migration_script:
                migration_path = "/".join(
                    [
                        rec.module_branch_id.addons_path or ".",
                        rec.module_branch_id.module_name,
                        "migrations",
                        rec.manifest_value,
                    ]
                )
                rb = rec.module_branch_id.repository_branch_id
                branch_name = rb.cloned_branch or rb.branch_id.name
                rec.migration_script_url = repo._get_resource_url(
                    branch_name, migration_path
                )

    def _to_dict(self):
        """Convert version data to a dictionary."""
        self.ensure_one()
        return {
            "name": self.name,
            "manifest_value": self.manifest_value,
            "commit": self.commit,
            "has_migration_script": self.has_migration_script,
            "sequence": self.sequence,
        }
