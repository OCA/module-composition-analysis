# Copyright 2025 Camptocamp SA
# Copyright 2026  Akretion (https://www.akretion.com).
# @author Sébastien Alix <sebastien.alix@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class OdooModuleBranchTimeline(models.Model):
    _name = "odoo.module.branch.timeline"
    _description = "Odoo Module Timeline (renaming/replacement)"
    _order = "odoo_version_sequence"

    module_branch_id = fields.Many2one(
        string="Module",
        comodel_name="odoo.module.branch",
        required=True,
        index=True,
    )
    last_known_module_branch_id = fields.Many2one(
        string="Last Known Module",
        comodel_name="odoo.module.branch",
        compute="_compute_last_known_module_branch_id",
        help="Technical field to check if current selected module is the last one.",
    )
    org_id = fields.Many2one(
        string="Organization",
        related="module_branch_id.org_id",
        store=True,
        index=True,
    )
    repository_id = fields.Many2one(
        string="Repository",
        related="module_branch_id.repository_id",
        store=True,
        index=True,
    )
    odoo_version_id = fields.Many2one(
        string="Starting from version",
        related="module_branch_id.branch_id.next_id",
        store=True,
        index=True,
    )
    odoo_version_sequence = fields.Integer(
        related="odoo_version_id.sequence",
        store=True,
    )
    state = fields.Selection(
        selection=[
            ("renamed", "has been renamed to"),
            ("replaced", "has been replaced by"),
        ],
        default="renamed",
        required=True,
        index=True,
        help=(
            "Renamed: modules still share the same Git history (it allows to "
            "check commits that could be ported)\n"
            "Replaced: module has been replaced (or merged) by another one that "
            "fulfill the same feature"
        ),
    )
    next_module_id = fields.Many2one(
        string="New module name",
        comodel_name="odoo.module",
        ondelete="restrict",
        index=True,
    )
    next_module_branch_id = fields.Many2one(
        string="New module",
        related="module_branch_id.next_odoo_version_module_branch_id",
    )
    note = fields.Html()
    migration_ids = fields.Many2many(
        comodel_name="odoo.module.branch.migration",
        string="Migrations",
        compute="_compute_migration_ids",
    )
    migration_scan = fields.Boolean(
        compute="_compute_migration_scan",
        help="Technical field telling if this timeline needs a migration scan.",
    )
    active = fields.Boolean(default=True)

    @api.depends("odoo_version_id", "module_branch_id", "next_module_id")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = (
                f"[{rec.odoo_version_id.name}] "
                f"{rec.module_branch_id.module_id.name} > {rec.next_module_id.name}"
            )

    @api.depends("module_branch_id")
    def _compute_last_known_module_branch_id(self):
        for rec in self:
            rec.last_known_module_branch_id = self.env["odoo.module.branch"].search(
                [
                    ("module_id", "=", rec.module_branch_id.module_id.id),
                    ("repository_id", "!=", False),
                    ("installable", "=", True),
                    (
                        "branch_id.sequence",
                        ">=",
                        rec.module_branch_id.branch_id.sequence,
                    ),
                ],
                order="branch_sequence DESC",
                limit=1,
            )

    @api.depends("module_branch_id", "next_module_id", "odoo_version_id")
    def _compute_migration_ids(self):
        for rec in self:
            current_module = rec.module_branch_id.module_id
            next_module = rec.next_module_id
            impacted_modules = current_module + next_module
            rec.migration_ids = (
                self.env["odoo.module.branch.migration"]
                .search(
                    [
                        (
                            "target_branch_id.sequence",
                            ">=",
                            rec.odoo_version_id.sequence,
                        ),
                        "|",
                        "|",
                        ("module_id", "=", current_module.id),
                        ("renamed_to_module_id", "in", impacted_modules.ids),
                        ("replaced_by_module_id", "in", impacted_modules.ids),
                    ]
                )
                .sudo()
            )

    def _compute_migration_scan(self):
        for rec in self:
            rec.migration_scan = any(rec.migration_ids.mapped("migration_scan"))

    # Update relevant migration records on timeline update.
    #
    # When a module is renamed or replaced, we refresh all impacted
    # migration data records and reset their last scan commits to trigger
    # a new migration scan.
    #
    # E.g.
    #     if a module on 17.0 is set as renamed starting from 18.0, existing
    #     migration data (17.0 -> 18.0, or 17.0 -> 19.0) will be aware of such
    #     change and all related modules will have to be scanned again.

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.migration_ids.force_update()
        return records

    @api.model
    def write(self, vals):
        migrations = self.migration_ids
        res = super().write(vals)
        (self.migration_ids | migrations).force_update()
        return res

    def unlink(self):
        migrations = self.migration_ids
        res = super().unlink()
        migrations.force_update()
        return res

    def open_migrations(self):
        self.ensure_one()
        xml_id = "odoo_repository_migration.odoo_module_branch_migration_action"
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        action["domain"] = [("id", "in", self.migration_ids.ids)]
        return action

    def action_scan(self):
        self.migration_ids.module_branch_id.repository_branch_id.action_scan()
        return True

    def _get_related_timelines(self):
        """Return timelines related to current ones regarding impacted modules.

        A module A could be renamed to a module B in version X, then renamed
        again to C in version X+1, etc.
        When calling this method on any timeline, the others are returned.
        """
        impacted_modules = self._get_all_impacted_modules()
        return self.search(
            [
                "|",
                ("module_branch_id.module_id", "in", impacted_modules.ids),
                ("next_module_id", "in", impacted_modules.ids),
            ]
        )

    # TODO: add ormcache?
    def _get_all_impacted_modules(self, visited=None):
        """Recursively collect all modules involved in the chain of timelines."""
        if visited is None:
            visited = self.env["odoo.module.branch.timeline"].browse()
        impacted_modules = self.env["odoo.module"].browse()
        for rec in self:
            if rec in visited:
                continue
            visited |= rec
            impacted_modules |= rec.module_branch_id.module_id + rec.next_module_id
            # Find previous timelines (current module is next_module_id)
            previous_timelines = self.search(
                [
                    ("next_module_id", "=", rec.module_branch_id.module_id.id),
                ]
            )
            for timeline in previous_timelines:
                impacted_modules |= timeline._get_all_impacted_modules(visited)
            # Find next timelines (next_module_id is the module_branch_id)
            next_timelines = self.search(
                [
                    ("module_branch_id.module_id", "=", rec.next_module_id.id),
                ]
            )
            for timeline in next_timelines:
                impacted_modules |= timeline._get_all_impacted_modules(visited)
        return impacted_modules
