# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class OdooProjectModuleMigration(models.Model):
    _name = "odoo.project.module.migration"
    # TODO test to inherit from 'module_migration_id' field too
    _inherits = {"odoo.module.branch": "source_module_branch_id"}
    _description = "Module migration line of an Odoo Project"
    _order = (
        "is_standard DESC, is_enterprise, is_community DESC, repository_id, module_name"
    )

    _sql_constraints = [
        (
            "uniq",
            "UNIQUE (odoo_project_id, migration_path_id, source_module_branch_id)",
            "This module migration path already exists.",
        ),
    ]

    odoo_project_id = fields.Many2one(
        comodel_name="odoo.project",
        ondelete="cascade",
        string="Project",
        required=True,
        index=True,
        readonly=True,
    )
    migration_path_id = fields.Many2one(
        comodel_name="odoo.migration.path",
        ondelete="restrict",
        string="Migration Path",
        required=True,
        index=True,
        readonly=True,
    )
    source_module_branch_id = fields.Many2one(
        comodel_name="odoo.module.branch",
        ondelete="restrict",
        string="Source",
        required=True,
        index=True,
        readonly=True,
    )
    target_module_branch_id = fields.Many2one(
        comodel_name="odoo.module.branch",
        ondelete="restrict",
        string="Target",
        compute="_compute_target_module_branch_id",
        store=True,
        index=True,
    )
    module_id = fields.Many2one(
        related="source_module_branch_id.module_id",
        store=True,
        index=True,
    )
    module_migration_id = fields.Many2one(
        comodel_name="odoo.module.branch.migration",
        ondelete="restrict",
        string="Migration",
        compute="_compute_module_migration_id",
        store=True,
        index=True,
    )
    state = fields.Selection(
        # Same as in 'odoo.module.branch.migration' but set a state even for
        # modules with no migration data, could be Odoo S.A. std modules
        # or project specific ones.
        selection=[
            ("fully_ported", "Fully Ported"),
            ("migrate", "To migrate"),
            ("port_commits", "Commits to port"),
            ("review_migration", "Migration to review"),
            # New states to qualify modules without migration data
            ("available", "Available"),
            ("removed", "Removed"),
        ],
        string="Migration status",
        compute="_compute_state",
        store=True,
        index=True,
    )
    results_text = fields.Text(related="module_migration_id.results_text")
    pr_url = fields.Char(related="module_migration_id.pr_url")

    @api.depends("source_module_branch_id", "migration_path_id")
    def _compute_target_module_branch_id(self):
        for rec in self:
            rec.target_module_branch_id = rec.source_module_branch_id.search(
                [
                    ("module_id", "=", rec.source_module_branch_id.module_id.id),
                    ("branch_id", "=", rec.migration_path_id.target_branch_id.id),
                    ("installable", "=", True),
                ]
            )

    @api.depends("migration_path_id", "source_module_branch_id")
    def _compute_module_migration_id(self):
        migration_model = self.env["odoo.module.branch.migration"]
        for rec in self:
            rec.module_migration_id = migration_model.search(
                [
                    ("migration_path_id", "=", rec.migration_path_id.id),
                    ("module_branch_id", "=", rec.source_module_branch_id.id),
                ]
            )

    @api.depends("module_migration_id.state")
    def _compute_state(self):
        for rec in self:
            rec.state = rec.module_migration_id.state
            if not rec.module_migration_id:
                # Default state (used by project specific modules)
                rec.state = "migrate"
                # Odoo S.A. modules
                if rec.source_module_branch_id.is_standard:
                    rec.state = (
                        "available" if rec.target_module_branch_id else "removed"
                    )
