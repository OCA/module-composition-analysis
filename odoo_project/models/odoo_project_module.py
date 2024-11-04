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
    installed_version = fields.Char(help="Installed version in project database.")
    installed_version_id = fields.Many2one(
        comodel_name="odoo.module.branch.version",
        string="Nearest installed version",
        help=(
            "If the real installed version is not available in the history of "
            "versions (could come from a pending merge not scanned), this field "
            "computes the nearest version available."
        ),
        compute="_compute_installed_version_id",
    )
    to_upgrade = fields.Boolean(
        compute="_compute_to_upgrade",
        store=True,
    )
    migration_scripts = fields.Boolean(
        compute="_compute_migration_scripts",
        store=True,
        help="Available migration scripts between installed and last version.",
    )
    installed_reverse_dependency_ids = fields.Many2many(
        comodel_name="odoo.project.module",
        compute="_compute_installed_reverse_dependency_ids",
        string="Installed Reverse Dependencies",
    )
    not_installed_reverse_dependency_ids = fields.Many2many(
        comodel_name="odoo.module.branch",
        compute="_compute_installed_reverse_dependency_ids",
        string="Not Installed Reverse Dependencies",
    )

    @api.depends("installed_version")
    def _compute_installed_version_id(self):
        for rec in self:
            rec.installed_version_id = rec.version_ids.browse()
            if not rec.installed_version:
                continue
            # Installed version could not be available in inventoried versions
            # if it is coming from a pending-merge. In such case we take the
            # nearest version matching the installed one.
            #   - Available versions upstream = "14.0.2.0.0" & "14.0.2.1.0"
            #   - Installed version  = "14.0.2.0.1" (in a pending-merge)
            #   - Computed installed version = "14.0.2.0.0"
            inst_ver = [int(n) for n in rec.installed_version.split(".")]
            for version in rec.version_ids.sorted("sequence"):
                ver = [int(n) for n in version.name.split(".")]
                if ver > inst_ver:
                    break
                rec.installed_version_id = version

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
            installed_version = rec.installed_version_id
            versions_with_mig_script = rec.version_ids.filtered(
                lambda v: (
                    v.sequence > installed_version.sequence and v.has_migration_script
                )
            )
            rec.migration_scripts = bool(versions_with_mig_script)

    @api.depends("odoo_project_id", "reverse_dependency_ids")
    def _compute_installed_reverse_dependency_ids(self):
        for rec in self:
            installed_project_modules = rec.odoo_project_id.project_module_ids
            installed_modules = installed_project_modules.module_branch_id
            installed_reverse_dependencies = rec.reverse_dependency_ids.filtered(
                lambda dep: dep in installed_modules
            )
            # Installed rev. deps. are 'odoo.project.module' records
            rec.installed_reverse_dependency_ids = (
                installed_reverse_dependencies.odoo_project_module_ids.filtered_domain(
                    [("odoo_project_id", "=", rec.odoo_project_id.id)]
                )
            )
            # Not installed rev. deps. are 'odoo.module.branch' records
            rec.not_installed_reverse_dependency_ids = (
                rec.reverse_dependency_ids - installed_reverse_dependencies
            )

    def open_recursive_dependencies(self):
        self.ensure_one()
        xml_id = "odoo_project.odoo_project_module_action_recursive_dependencies"
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        action["name"] = "All dependencies"
        dependencies = self.module_branch_id._get_recursive_dependencies()
        project_dependencies = dependencies.odoo_project_module_ids.filtered(
            lambda o: o.odoo_project_id == self.odoo_project_id
        )
        action["domain"] = [("id", "in", project_dependencies.ids)]
        return action

    def _remap_to_specific_module(self):
        """Re-map orphaned project modules.

        As soon as an orphaned module has been scanned as a specific module
        of a project repository, all project modules that were targeting this
        orphaned module will inherit from this newly specific module instead.
        """
        for rec in self:
            if not rec.odoo_project_id.repository_id:
                continue
            specific_module_branch = self.env["odoo.module.branch"]._get_module_branch(
                rec.branch_id,
                rec.module_id,
                repo=rec.odoo_project_id.repository_id,
            )
            if specific_module_branch:
                rec.write({"module_branch_id": specific_module_branch.id})
