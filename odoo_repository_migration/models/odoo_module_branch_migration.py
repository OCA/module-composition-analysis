# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import pprint

from odoo import api, fields, models


class OdooModuleBranchMigration(models.Model):
    _name = "odoo.module.branch.migration"
    _description = "Migration data for a module of a given branch."
    _order = "display_name"

    display_name = fields.Char(compute="_compute_display_name", store=True)
    module_branch_id = fields.Many2one(
        comodel_name="odoo.module.branch",
        ondelete="cascade",
        string="Module",
        required=True,
        index=True,
    )
    module_id = fields.Many2one(
        related="module_branch_id.module_id",
        store=True,
        index=True,
    )
    org_id = fields.Many2one(related="module_branch_id.org_id", store=True)
    repository_id = fields.Many2one(
        related="module_branch_id.repository_id",
        store=True,
        ondelete="cascade",
    )
    migration_path_id = fields.Many2one(
        comodel_name="odoo.migration.path",
        ondelete="cascade",
        required=True,
        index=True,
    )
    source_branch_id = fields.Many2one(
        related="migration_path_id.source_branch_id",
        store=True,
        index=True,
    )
    target_branch_id = fields.Many2one(
        related="migration_path_id.target_branch_id",
        store=True,
        index=True,
    )
    author_ids = fields.Many2many(related="module_branch_id.author_ids")
    maintainer_ids = fields.Many2many(related="module_branch_id.maintainer_ids")
    process = fields.Char(index=True)
    state = fields.Selection(
        selection=[
            ("fully_ported", "Fully Ported"),
            ("migrate", "To migrate"),
            ("port_commits", "Commits to port"),
            ("review_migration", "Migration to review"),
        ],
        string="Migration Status",
        compute="_compute_state",
        store=True,
        index=True,
    )
    pr_url = fields.Char(
        string="PR URL",
        compute="_compute_pr_url",
        store=True,
    )
    results = fields.Serialized()
    results_text = fields.Text(compute="_compute_results_text")
    last_source_scanned_commit = fields.Char()
    last_target_scanned_commit = fields.Char()

    _sql_constraints = [
        (
            "module_migration_path_uniq",
            "UNIQUE (module_branch_id, migration_path_id)",
            "This module migration path already exists."
        ),
    ]

    @api.depends(
        "module_branch_id.module_id",
        "source_branch_id.name",
        "target_branch_id.name",
    )
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = (
                f"{rec.module_branch_id.module_id.name}: "
                f"{rec.source_branch_id.name} -> {rec.target_branch_id.name}"
            )

    @api.depends("process", "pr_url")
    def _compute_state(self):
        for rec in self:
            rec.state = rec.process or "fully_ported"
            if rec.process == "migrate" and rec.pr_url:
                rec.state = "review_migration"

    @api.depends("results")
    def _compute_pr_url(self):
        for rec in self:
            rec.pr_url = rec.results.get("existing_pr", {}).get("url")

    @api.depends("results")
    def _compute_results_text(self):
        for rec in self:
            rec.results_text = pprint.pformat(rec.results)

    @api.model
    @api.returns("odoo.module.branch.migration")
    def push_scanned_data(self, module_branch_id, data):
        migration_path = self.env["odoo.migration.path"].search(
            [
                ("source_branch_id", "=", data["source_branch"]),
                ("target_branch_id", "=", data["target_branch"]),
            ]
        )
        values = {
            "module_branch_id": module_branch_id,
            "migration_path_id": migration_path.id,
            "last_source_scanned_commit": data["source_commit"],
            "last_target_scanned_commit": data["target_commit"],
        }
        for key in ("process", "results"):
            if data.get(key):
                values[key] = data[key]
        return self._create_or_update(module_branch_id, migration_path, values)

    def _create_or_update(self, module_branch_id, migration_path, values):
        args = [
            ("module_branch_id", "=", module_branch_id),
            ("source_branch_id", "=", migration_path.source_branch_id.id),
            ("target_branch_id", "=", migration_path.target_branch_id.id),
        ]
        migration = self.search(args)
        if migration:
            migration.sudo().write(values)
        else:
            migration = self.sudo().create(values)
        return migration
