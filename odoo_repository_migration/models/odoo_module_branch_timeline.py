# Copyright 2025 Camptocamp SA
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
        inverse="_inverse_next_fields",
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
        inverse="_inverse_next_fields",
        ondelete="restrict",
        index=True,
    )
    next_module_branch_id = fields.Many2one(
        string="New module",
        related="module_branch_id.next_odoo_version_module_branch_id",
    )
    note = fields.Html()

    @api.depends("odoo_version_id", "module_branch_id", "next_module_id")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = (
                f"[{rec.odoo_version_id.name}] "
                f"{rec.module_branch_id.module_id.name} > {rec.next_module_id.name}"
            )

    def _inverse_next_fields(self):
        # When a module is renamed or replaced, we reset the
        # last target scan commits on all impacted migration paths.
        # E.g.
        #   if a module on 17.0 is set as renamed starting from 18.0,
        #   all migration paths of this module targetting versions >= 18.0
        #   should re-trigger a migration scan.
        for rec in self:
            migrations = (
                self.env["odoo.module.branch.migration"]
                .search(
                    [
                        ("module_id", "=", rec.module_branch_id.module_id.id),
                        (
                            "target_branch_id.sequence",
                            ">=",
                            rec.odoo_version_id.sequence,
                        ),
                    ]
                )
                .sudo()
            )
            migrations.last_target_scanned_commit = False
            migrations._compute_renamed_to_module_id()
            migrations._compute_replaced_by_module_id()
            migrations._compute_state()

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
