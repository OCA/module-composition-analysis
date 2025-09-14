# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, fields, models


class OdooModuleBranch(models.Model):
    _inherit = "odoo.module.branch"

    timeline_ids = fields.One2many(
        comodel_name="odoo.module.branch.timeline",
        inverse_name="module_branch_id",
        string="Timeline",
    )
    next_odoo_version_module_branch_id = fields.Many2one(
        comodel_name="odoo.module.branch",
        compute="_compute_next_odoo_version_module_branch_id",
        string="Next Odoo Version Module Branch",
    )
    migration_ids = fields.One2many(
        comodel_name="odoo.module.branch.migration",
        inverse_name="module_branch_id",
        string="Migrations",
    )
    migration_scan = fields.Boolean(
        compute="_compute_migration_scan",
        store=True,
        help="Technical field telling if this module is elligible for a migration scan.",
    )

    @api.depends("branch_id.next_id", "timeline_ids")
    def _compute_next_odoo_version_module_branch_id(self):
        for rec in self:
            rec.next_odoo_version_module_branch_id = False
            # Stop there if no next version
            if not rec.branch_id.next_id:
                continue
            # Look for the next available version for this module name
            rec.next_odoo_version_module_branch_id = self.search(
                [
                    ("branch_sequence", ">=", rec.branch_id.next_id.sequence),
                    ("module_id", "=", rec.module_id.id),
                ],
                order="branch_sequence",
                limit=1,
            )
            # Stop there if no renaming/relacement
            if not rec.timeline_ids:
                continue
            rec.next_odoo_version_module_branch_id = self.search(
                [
                    ("branch_sequence", ">=", rec.branch_id.next_id.sequence),
                    ("module_id", "=", rec.timeline_ids.next_module_id.id),
                ],
                order="branch_sequence",
                limit=1,
            )

    def _replaced_by_module_in_target_version(self, target_branch):
        """Return the module replacing current one in last module versions.

        Look for current + next modules as the migration scan could do a jump
        14.0 -> 18.0, while a module has been replaced starting from 18.0 (and
        therefore flagged as replaced in 17.0 module data).

        We give the priority to last modules while checking them.
        """
        self.ensure_one()
        modules = self._get_next_versions(target_branch)
        for module in modules.sorted(
            key=lambda mod: mod.branch_id.sequence, reverse=True
        ):
            if module.timeline_ids.state == "replaced":
                return module.timeline_ids.next_module_id
        return self.env["odoo.module"]

    def _renamed_to_module_in_target_version(self, target_branch):
        """Return the new module technical name in last module versions.

        Look for current + next modules as the migration scan could do a jump
        14.0 -> 18.0, while a module has been renamed starting from 18.0 (and
        therefore flagged as renamed in 17.0 module data).

        We give the priority to last modules while checking them.
        """
        self.ensure_one()
        modules = self._get_next_versions(target_branch)
        for module in modules.sorted(
            key=lambda mod: mod.branch_id.sequence, reverse=True
        ):
            if module.timeline_ids.state == "renamed":
                return module.timeline_ids.next_module_id
        return self.env["odoo.module"]

    def _get_next_versions(self, target_branch):
        self.ensure_one()
        return self.env["odoo.module.branch"].search(
            [
                ("module_id", "=", self.module_id.id),
                ("branch_id.sequence", ">=", self.branch_id.sequence),
                ("branch_id.sequence", "<", target_branch.sequence),
            ]
        )

    def _get_next_module_branches(self, target_branch=None):
        """Return all modules in the right version order starting from current one.

        This is taking into account module renamed or replaced in intermediate versions.
        """
        if not self:
            return self.browse()
        self.ensure_one()
        if target_branch:
            assert self.branch_id.sequence < target_branch.sequence
        next_module_branch = self.next_odoo_version_module_branch_id
        next_module_branch_ids = []
        while next_module_branch:
            if (
                target_branch
                and next_module_branch.branch_id.sequence > target_branch.sequence
            ):
                break
            next_module_branch_ids.append(next_module_branch.id)
            next_module_branch = next_module_branch.next_odoo_version_module_branch_id
        return self.browse(next_module_branch_ids)

    @api.depends(
        "removed",
        "pr_url",
        "last_scanned_commit",
        "migration_ids.migration_scan",
        "repository_id.collect_migration_data",
    )
    def _compute_migration_scan(self):
        for rec in self:
            # Do not scan removed or pending (in PR) modules
            if rec.removed or rec.pr_url:
                rec.migration_scan = False
                continue
            # Default repository migration scan policy
            rec.migration_scan = rec.repository_id.collect_migration_data
            if not rec.migration_scan:
                continue
            # Repository scan has to be performed first
            if not rec.last_scanned_commit:
                continue
            # Migration scan to do as soon as a migration path is missing
            # among existing scans. However, we remove migration path that doesn't
            # match branches scanned in the repository (e.g. 18.0 branch could
            # be missing in a repo while a migration path 16.0 -> 18.0 is
            # configured, so no need to do a migration scan in this case).
            available_repo_branches = rec.repository_id.branch_ids.branch_id
            available_migration_paths = self.env["odoo.migration.path"].search(
                [
                    ("source_branch_id", "=", rec.branch_id.id),
                    ("target_branch_id", "in", available_repo_branches.ids),
                ]
            )
            scanned_migration_paths = rec.migration_ids.migration_path_id
            if available_migration_paths != scanned_migration_paths:
                rec.migration_scan = True
                continue
            # Migration scan to do if any of the migration path requires one
            rec.migration_scan = any(rec.migration_ids.mapped("migration_scan"))

    def _to_dict(self):
        # Add the migrations data
        data = super()._to_dict()
        data["migrations"] = []
        for migration in self.migration_ids:
            data["migrations"].append(migration._to_dict())
        return data

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs._update_migration_target_module_id()
        return recs

    def write(self, vals):
        res = super().write(vals)
        # When 'pr_url' is set or unset, this means the module has been found
        # in a PR or has been merged upstream. We want to recompute the target
        # module in migration data in such case.
        if "pr_url" in vals:
            self._update_migration_target_module_id()
        return res

    def _update_migration_target_module_id(self):
        """Update `target_module_id` field on relevant module migration records."""
        for rec in self:
            migrations = self.env["odoo.module.branch.migration"].search(
                [
                    ("module_id", "=", rec.module_id.id),
                    ("target_branch_id", "=", rec.branch_id.id),
                ]
            )
            # Recompute 'target_module_id' field
            migrations._compute_target_module_branch_id()

    def open_next_module_branches(self):
        self.ensure_one()
        xml_id = "odoo_repository.odoo_module_branch_action"
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        action["name"] = _("Next versions")
        action["domain"] = [("id", "in", self._get_next_module_branches().ids)]
        return action
