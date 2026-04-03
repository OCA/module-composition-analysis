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
        string="Source",
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
    target_module_branch_id = fields.Many2one(
        comodel_name="odoo.module.branch",
        ondelete="cascade",
        string="Target",
        compute="_compute_target_module_branch_id",
        store=True,
        index=True,
    )
    author_ids = fields.Many2many(related="module_branch_id.author_ids")
    maintainer_ids = fields.Many2many(related="module_branch_id.maintainer_ids")
    process = fields.Char(index=True)
    moved_to_standard = fields.Boolean(
        compute="_compute_moved_to_standard",
        store=True,
        help=(
            "Module now available in Odoo standard code. "
            "This module is maybe not exactly the same, and doesn't have the "
            "same scope so it deserves a check during a migration."
        ),
    )
    moved_to_oca = fields.Boolean(
        compute="_compute_moved_to_oca",
        store=True,
        help=(
            "Module now available in OCA. "
            "This module is maybe not exactly the same, and doesn't have the "
            "same scope so it deserves a check during a migration."
        ),
    )
    moved_to_generic = fields.Boolean(
        compute="_compute_moved_to_generic",
        store=True,
        string="Now generic",
        help=(
            "Specific module now available in a generic repository. "
            "This module is maybe not exactly the same, and doesn't have the "
            "same scope so it deserves a check during a migration."
        ),
    )
    renamed_to_module_id = fields.Many2one(
        comodel_name="odoo.module",
        compute="_compute_renamed_to_module_id",
        string="Renamed to",
        store=True,
        index=True,
    )
    replaced_by_module_id = fields.Many2one(
        comodel_name="odoo.module",
        compute="_compute_replaced_by_module_id",
        string="Replaced by",
        store=True,
        index=True,
    )
    state = fields.Selection(
        selection=[
            ("fully_ported", "Fully Ported"),
            ("migrate", "To migrate"),
            ("port_commits", "Ported (missing commits?)"),
            ("review_migration", "To review"),
            ("replaced", "Replaced"),
            ("moved_to_standard", "Moved to standard?"),
            ("moved_to_oca", "Moved to OCA"),
            ("moved_to_generic", "Moved to generic repo"),
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
    active = fields.Boolean(related="migration_path_id.active", store=True)
    migration_scan = fields.Boolean(
        compute="_compute_migration_scan",
        store=True,
        help="Technical field telling if this migration path needs a migration scan.",
    )

    _sql_constraints = [
        (
            "module_migration_path_uniq",
            "UNIQUE (module_branch_id, migration_path_id)",
            "This module migration path already exists.",
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

    @api.depends(
        "module_branch_id",
        "migration_path_id",
        "replaced_by_module_id",
        "renamed_to_module_id",
    )
    def _compute_target_module_branch_id(self):
        module_branch_model = self.env["odoo.module.branch"]
        for rec in self:
            # Look for the right module technical name
            module = (
                rec.replaced_by_module_id
                or rec.renamed_to_module_id
                or rec.module_branch_id.module_id
            )
            rec.target_module_branch_id = module_branch_model._find(
                rec.migration_path_id.target_branch_id,
                module,
                rec.module_branch_id.repository_id,
                domain=[("installable", "=", True)],
            )

    @api.depends("module_branch_id.is_standard", "target_module_branch_id.is_standard")
    def _compute_moved_to_standard(self):
        for rec in self:
            rec.moved_to_standard = (
                not rec.module_branch_id.is_standard
                and rec.target_module_branch_id.is_standard
            )

    @api.depends("org_id", "target_module_branch_id.org_id")
    def _compute_moved_to_oca(self):
        org_oca = self.env.ref(
            "odoo_repository.odoo_repository_org_oca", raise_if_not_found=False
        )
        for rec in self:
            rec.moved_to_oca = False
            if not org_oca:
                continue
            rec.moved_to_oca = (
                rec.org_id != org_oca and rec.target_module_branch_id.org_id == org_oca
            )

    @api.depends(
        "repository_id.specific", "target_module_branch_id.repository_id.specific"
    )
    def _compute_moved_to_generic(self):
        for rec in self:
            rec.moved_to_generic = (
                rec.repository_id.specific
                and rec.target_module_branch_id.repository_id
                and not rec.target_module_branch_id.repository_id.specific
            )

    @api.depends(
        "module_branch_id.timeline_ids.state",
        "module_branch_id.timeline_ids.next_module_id",
        "target_branch_id",
    )
    def _compute_renamed_to_module_id(self):
        for rec in self:
            rec.renamed_to_module_id = (
                rec.module_branch_id._renamed_to_module_in_target_version(
                    rec.target_branch_id
                )
            )

    @api.depends(
        "module_branch_id.timeline_ids.state",
        "module_branch_id.timeline_ids.next_module_id",
        "target_branch_id",
    )
    def _compute_replaced_by_module_id(self):
        for rec in self:
            rec.replaced_by_module_id = (
                rec.module_branch_id._replaced_by_module_in_target_version(
                    rec.target_branch_id
                )
            )

    @api.depends(
        "replaced_by_module_id",
        "process",
        "pr_url",
        "moved_to_standard",
        "moved_to_oca",
        "moved_to_generic",
    )
    def _compute_state(self):
        for rec in self:
            if rec.replaced_by_module_id:
                # Module replaced by another one
                rec.state = "replaced"
                continue
            if rec.moved_to_standard:
                # Module moved to a standard repository (likely from OCA to
                # odoo/odoo, like 'l10n_eu_oss', 'knowledge', ...).
                # E.g. this could tell integrators that a module like
                # 'l10n_eu_oss_oca' should now be used instead.
                rec.state = "moved_to_standard"
                continue
            if rec.moved_to_oca:
                # Module moved to an OCA repository
                rec.state = "moved_to_oca"
                continue
            if rec.moved_to_generic:
                # Specific module moved to a generic repository (public or private)
                rec.state = "moved_to_generic"
                continue
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

    @api.depends(
        "module_branch_id.last_scanned_commit",
        "replaced_by_module_id",
        "repository_id.collect_migration_data",
        "last_source_scanned_commit",
        "last_target_scanned_commit",
        "pr_url",
        "target_module_branch_id.pr_url",
        "target_module_branch_id.last_scanned_commit",
        "state",
    )
    def _compute_migration_scan(self):
        # Migration scan to do if last scanned commit doesn't match the last
        # migration scan, both for source and target modules.
        for rec in self:
            rec.migration_scan = False
            # No migration scan if repository is not configured to do it
            if not rec.repository_id.collect_migration_data:
                continue
            # No migration scan for modules moved to Odoo/OCA/generic repo
            if rec.state and rec.state.startswith("moved_to"):
                continue
            # No migration scan for modules replaced by another module
            if rec.replaced_by_module_id:
                continue
            if (
                rec.last_source_scanned_commit
                != rec.module_branch_id.last_scanned_commit
            ):
                rec.migration_scan = True
            elif (
                rec.target_module_branch_id.last_scanned_commit
                and rec.last_target_scanned_commit
                != rec.target_module_branch_id.last_scanned_commit
            ):
                rec.migration_scan = True
            elif rec.target_module_branch_id.pr_url != rec.pr_url:
                rec.migration_scan = True

    @api.model
    @api.returns("odoo.module.branch.migration")
    def push_scanned_data(self, module_branch_id, data):
        migration_path = self.env["odoo.migration.path"].search(
            [
                ("source_branch_id", "=", data["source_version"]),
                ("target_branch_id", "=", data["target_version"]),
            ]
        )
        values = {
            "module_branch_id": module_branch_id,
            "migration_path_id": migration_path.id,
            "last_source_scanned_commit": data["source_commit"],
            "last_target_scanned_commit": data["target_commit"],
        }
        # Update migration data only if a migration scan occured
        if "report" in data:
            values["process"] = data["report"].get("process", False)
            values["results"] = data["report"].get("results", {})
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

    def _to_dict(self):
        self.ensure_one()
        return {
            "source_branch": self.source_branch_id.name,
            "target_branch": self.target_branch_id.name,
            "process": self.process,
            "results": self.results,
            "last_source_scanned_commit": self.last_source_scanned_commit,
            "last_target_scanned_commit": self.last_target_scanned_commit,
        }
