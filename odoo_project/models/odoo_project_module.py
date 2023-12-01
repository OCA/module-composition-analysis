# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models
from odoo.tools.parse_version import parse_version as v


class OdooProjectModule(models.Model):
    _name = "odoo.project.module"
    _inherits = {"odoo.module.branch": "module_branch_id"}
    _description = "Odoo Project Module"
    _order = "name"

    odoo_project_id = fields.Many2one(
        comodel_name="odoo.project",
        ondelete="cascade",
        string="Project",
    )
    module_branch_id = fields.Many2one(
        comodel_name="odoo.module.branch",
        ondelete="cascade",
        string="Upstream Module",
        required=True,
    )
    installed_version = fields.Char()
    to_upgrade = fields.Boolean(
        compute="_compute_to_upgrade",
        store=True,
    )
    migration_scripts = fields.Boolean(
        compute="_compute_migration_scripts",
        store=True,
        help="Available migration scripts between installed and last version.",
    )

    @api.depends("version", "installed_version")
    def _compute_to_upgrade(self):
        for rec in self:
            rec.to_upgrade = False
            installed_version = rec.installed_version or rec.version
            if installed_version and rec.version:
                rec.to_upgrade = v(installed_version) < v(rec.version)

    @api.depends(
        "to_upgrade",
        "installed_version",
        "version_ids.name",
        "version_ids.has_migration_script",
    )
    def _compute_migration_scripts(self):
        for rec in self:
            rec.migration_scripts = False
            if not rec.to_upgrade:
                continue
            installed_version = rec._get_installed_version()
            versions_with_mig_script = rec.version_ids.filtered(
                lambda v: (
                    v.sequence > installed_version.sequence and v.has_migration_script
                )
            )
            rec.migration_scripts = bool(versions_with_mig_script)

    def _get_installed_version(self):
        self.ensure_one()
        installed_version = self.version_ids.browse()
        if not self.installed_version:
            return installed_version
        # Installed version could not be available in inventoried versions
        # if it is coming from a pending-merge. In such case we take the last
        # matching version as the installed one.
        #   - Available versions upstream = "14.0.2.0.0" & "14.0.2.1.0"
        #   - Installed version  = "14.0.2.0.1" (in a pending-merge)
        #   - Computed installed version = "14.0.2.0.0"
        inst_ver = [int(n) for n in self.installed_version.split(".")]
        for version in self.version_ids.sorted("sequence"):
            ver = [int(n) for n in version.name.split(".")]
            if ver > inst_ver:
                break
            installed_version = version
        return installed_version
