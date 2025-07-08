# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class OdooProjectModuleMigration(models.Model):
    _name = "odoo.project.module.migration"
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
    project_module_id = fields.Many2one(
        comodel_name="odoo.project.module",
        ondelete="cascade",
        string="Installed Module",
        help="Version of the module installed in the project.",
        compute="_compute_project_module_id",
        store=True,
        index=True,
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
    migration_script_ids = fields.One2many(
        comodel_name="odoo.module.branch.version",
        string="Migration Scripts",
        help=(
            "Migration scripts available between the installed version and "
            "the last version available on the target branch.\n"
            "Ones that rework the database schema or data could be mandatory."
        ),
        compute="_compute_migration_script_ids",
    )
    state = fields.Selection(
        # Same as in 'odoo.module.branch.migration' but set a state even for
        # modules with no migration data, could be Odoo S.A. std modules
        # or project specific ones.
        selection=[
            ("fully_ported", "Fully Ported"),
            ("migrate", "To migrate"),
            ("port_commits", "Ported (missing commits?)"),
            ("review_migration", "To review"),
            ("replaced", "Replaced"),
            ("moved_to_standard", "Moved to standard?"),
            ("moved_to_oca", "Moved to OCA"),
            ("moved_to_generic", "Moved to generic repo"),
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

    @api.depends("odoo_project_id", "source_module_branch_id")
    def _compute_project_module_id(self):
        for rec in self:
            project_module = self.env["odoo.project.module"].search(
                [
                    ("odoo_project_id", "=", rec.odoo_project_id.id),
                    ("module_branch_id", "=", rec.source_module_branch_id.id),
                ],
                limit=1,
            )
            rec.project_module_id = project_module

    @api.depends(
        "source_module_branch_id",
        "migration_path_id",
        "module_migration_id.replaced_by_module_id",
        "module_migration_id.renamed_to_module_id",
    )
    def _compute_target_module_branch_id(self):
        module_branch_model = self.env["odoo.module.branch"]
        for rec in self:
            # Look for the right module technical name
            module = (
                rec.module_migration_id.replaced_by_module_id
                or rec.module_migration_id.renamed_to_module_id
                or rec.source_module_branch_id.module_id
            )
            rec.target_module_branch_id = module_branch_model._find(
                rec.migration_path_id.target_branch_id,
                module,
                rec.odoo_project_id.repository_id,
                domain=[("installable", "=", True)],
            )

    # NOTE: 'migration_scan' is here to re-trigger the computation
    # each time the source module has its state updated regarding migration.
    # FIXME: this could trigger too much computations on irrelevant records
    # (one not related to the updated migration path), we should switch to
    # component events to handle such cases.
    @api.depends("migration_path_id", "source_module_branch_id.migration_scan")
    def _compute_module_migration_id(self):
        migration_model = self.env["odoo.module.branch.migration"]
        for rec in self:
            rec.module_migration_id = migration_model.search(
                [
                    ("migration_path_id", "=", rec.migration_path_id.id),
                    ("module_branch_id", "=", rec.source_module_branch_id.id),
                ]
            )

    @api.depends("project_module_id")
    def _compute_migration_script_ids(self):
        for rec in self:
            version_model = rec.env["odoo.module.branch.version"]
            current_release_versions = version_model.search(
                [
                    ("module_branch_id", "=", rec.source_module_branch_id.id),
                    (
                        "sequence",
                        ">",
                        rec.project_module_id.installed_version_id.sequence,
                    ),
                    ("has_migration_script", "=", True),
                ],
                order="sequence",
            )
            # Collect versions with migration scripts accross next modules
            # taking into account module renaming/replacement
            target_branch = rec.migration_path_id.target_branch_id
            next_modules = rec.source_module_branch_id._get_next_module_branches(
                target_branch
            )
            new_release_versions = next_modules.version_ids.filtered(
                "has_migration_script"
            ).sorted(key=lambda v: (v.branch_sequence, v.sequence))
            rec.migration_script_ids = current_release_versions | new_release_versions

    @api.depends("module_migration_id.state")
    def _compute_state(self):
        for rec in self:
            rec.state = rec.module_migration_id.state
            if not rec.module_migration_id:
                # Default state (used by project specific modules)
                rec.state = "migrate"
                if rec.source_module_branch_id.is_standard:
                    # Odoo S.A. modules
                    rec.state = (
                        "available" if rec.target_module_branch_id else "removed"
                    )
                elif rec.target_module_branch_id:
                    # repo with collect_migration_data = False
                    rec.state = "available"
