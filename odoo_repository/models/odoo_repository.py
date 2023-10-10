# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import json
import os
import pathlib

import requests

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError

from odoo.addons.queue_job.delay import chain
from odoo.addons.queue_job.exception import RetryableJobError
from odoo.addons.queue_job.job import identity_exact

from ..utils.scanner import RepositoryScannerOdooEnv


class OdooRepository(models.Model):
    _name = "odoo.repository"
    _description = "Odoo Modules Repository"
    _order = "display_name"

    _repositories_path_key = "odoo_repository_storage_path"

    display_name = fields.Char(compute="_compute_display_name", store=True)
    active = fields.Boolean(default=True)
    org_id = fields.Many2one(
        comodel_name="odoo.repository.org",
        ondelete="cascade",
        string="Organization",
        required=True,
        index=True,
    )
    name = fields.Char(required=True, index=True)
    repo_url = fields.Char(
        string="Web URL",
        help="Web access to this repository.",
        required=True,
    )
    to_scan = fields.Boolean(
        default=True,
        help="Scan this repository to collect data.",
    )
    clone_url = fields.Char(
        string="Clone URL",
        help="Used to clone the repository.",
    )
    repo_type = fields.Selection(
        selection=[
            ("github", "GitHub"),
            ("gitlab", "GitLab"),
        ],
        required=True,
    )
    ssh_key_id = fields.Many2one(
        comodel_name="ssh.key",
        ondelete="restrict",
        string="SSH Key",
        help="SSH key used to clone/fetch this repository.",
    )
    clone_branch_id = fields.Many2one(
        comodel_name="odoo.branch",
        ondelete="restrict",
        string="Branch to clone",
        help="Branch to clone if different than configured ones",
        domain=[("odoo_version", "=", False)],
    )
    odoo_version_id = fields.Many2one(
        comodel_name="odoo.branch",
        ondelete="restrict",
        string="Odoo Version",
        domain=[("odoo_version", "=", True)],
    )
    active = fields.Boolean(default=True)
    addons_path_ids = fields.Many2many(
        comodel_name="odoo.repository.addons_path",
        string="Addons Path",
        help="Relative path of folders in this repository hosting Odoo modules",
    )
    branch_ids = fields.One2many(
        comodel_name="odoo.repository.branch",
        inverse_name="repository_id",
        string="Branches",
        readonly=True,
    )

    @api.model
    def default_get(self, fields_list):
        """'default_get' method overloaded."""
        res = super().default_get(fields_list)
        if "addons_path_ids" not in res:
            res["addons_path_ids"] = [
                (
                    4,
                    self.env.ref(
                        "odoo_repository.odoo_repository_addons_path_community"
                    ).id,
                )
            ]
        return res

    @api.depends("org_id", "name")
    def _compute_github_url(self):
        for rec in self:
            rec.github_url = f"{rec.org_id.github_url}/{rec.name}"

    _sql_constraints = [
        (
            "org_id_name_repository_id_uniq",
            "UNIQUE (org_id, name, odoo_version_id)",
            "This repository already exists.",
        ),
    ]

    @api.depends("org_id.name", "name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.org_id.name}/{rec.name}"

    @api.onchange("repo_url", "to_scan", "clone_url")
    def _onchange_repo_url(self):
        if not self.repo_url:
            return
        for type_, __ in self._fields["repo_type"].selection:
            if type_ not in self.repo_url:
                continue
            self.repo_type = type_
            if not self.clone_url and self.to_scan:
                self.clone_url = self.repo_url
            break

    @api.model
    def _get_odoo_branches_to_clone(self):
        return self.env["odoo.branch"].search([("odoo_version", "=", True)])

    @api.model
    def cron_scanner(self, branches=None, force=False):
        """Scan and collect Odoo repositories data.

        As the scanner is run on the same server than Odoo, a special class
        `RepositoryScannerOdooEnv` is used so the scanner can request Odoo
        through an environment (api.Environment).
        """
        repositories = self.search([("to_scan", "=", True)])
        if not branches:
            branches = self._get_odoo_branches_to_clone().mapped("name")
        for repo in repositories:
            repo.action_scan(branches=branches, force=force)

    def _check_config(self):
        # Check the configuration of repositories folder
        key = self._repositories_path_key
        repositories_path = self.env["ir.config_parameter"].get_param(key, "")
        if not repositories_path:
            raise UserError(
                _(
                    "Please define the '{key}' system parameter to "
                    "clone repositories in the folder of your choice.".format(key=key)
                )
            )
        # Ensure the folder exists
        pathlib.Path(repositories_path).mkdir(parents=True, exist_ok=True)

    def action_scan(self, branches=None, force=False):
        """Scan the whole repository."""
        self.ensure_one()
        if not self.to_scan:
            return False
        self._check_config()
        if self.clone_branch_id:
            branches = [self.clone_branch_id.name]
        if not branches:
            branches = self._get_odoo_branches_to_clone().mapped("name")
        if force:
            self._reset_scanned_commits()
        # Scan repository branches sequentially as they need to be checked out
        # to perform the analysis
        jobs = self._create_jobs(branches)
        chain(*jobs).delay()
        return True

    def _reset_scanned_commits(self):
        """Reset the scanned commits.

        This will make the next repository scan restarting from the beginning,
        and thus making it slower.
        """
        self.ensure_one()
        self.branch_ids.write({"last_scanned_commit": False})
        self.branch_ids.module_ids.sudo().write({"last_scanned_commit": False})

    def _create_jobs(self, branches):
        self.ensure_one()
        jobs = []
        for branch in branches:
            delayable = self.delayable(
                description=f"Scan {self.display_name}#{branch}",
                identity_key=identity_exact,
            )
            job = delayable._scan_branch(branch)
            jobs.append(job)
        return jobs

    def _scan_branch(self, branch):
        """Scan a repository branch"""
        try:
            params = self._prepare_scanner_parameters(branch)
            scanner = RepositoryScannerOdooEnv(**params)
            return scanner.scan()
        except Exception as exc:
            raise RetryableJobError("Scanner error") from exc

    def _prepare_scanner_parameters(self, branch):
        ir_config = self.env["ir.config_parameter"]
        repositories_path = ir_config.get_param(self._repositories_path_key)
        github_token = ir_config.get_param(
            "odoo_repository_github_token", os.environ.get("GITHUB_TOKEN")
        )
        return {
            "org": self.org_id.name,
            "name": self.name,
            "clone_url": self.clone_url,
            "branches": [branch],
            "addons_paths_data": self.addons_path_ids.read(
                [
                    "relative_path",
                    "is_standard",
                    "is_enterprise",
                    "is_community",
                ]
            ),
            "repositories_path": repositories_path,
            "ssh_key": self.ssh_key_id.private_key,
            "github_token": github_token,
            "env": self.env,
        }

    def action_force_scan(self, branches=None):
        """Force the scan of the repositories.

        It will restart the scan without considering the last scanned commit,
        overriding already collected module data if any.
        """
        self.ensure_one()
        return self.action_scan(branches=branches, force=True)

    @api.model
    def cron_fetch_data(self, branches=None, force=False):
        """Fetch Odoo repositories data from the main node (if any)."""
        main_node_url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("odoo_repository_main_node_url")
        )
        if not main_node_url:
            return False
        branches = self.env["odoo.branch"].search([("odoo_version", "=", True)])
        branch_names = ",".join(branches.mapped("name"))
        url = f"{main_node_url}?branches=%s" % branch_names
        try:
            response = requests.get(url, timeout=60)
        except Exception as exc:
            raise UserError(_("Unable to fetch data from %s") % main_node_url) from exc
        else:
            if response.status_code == 200:
                try:
                    data = json.loads(response.text)
                except json.decoder.JSONDecodeError as exc:
                    raise UserError(
                        _("Unable to decode data received from %s") % main_node_url
                    ) from exc
                else:
                    self._import_data(data)

    def _import_data(self, data):
        for module_data in data:
            # TODO Move these methods to 'odoo.module.branch'?
            values = self._prepare_module_branch_values(module_data)
            self._create_or_update_module_branch(values)

    def _prepare_module_branch_values(self, data):
        # Get branch, repository and technical module
        branch = self.env["odoo.branch"].search(
            [("odoo_version", "=", True), ("name", "=", data["branch"])]
        )
        org = self._get_repository_org(data["repository"]["org"])
        repository = self._get_repository(
            org.id, data["repository"]["name"], data["repository"]
        )
        repository_branch = self._get_repository_branch(
            org.id, repository.id, branch.id, data["repository"]
        )

        mb_model = self.env["odoo.module.branch"]
        module = mb_model._get_module(data["module"])
        # Prepare values
        category_id = mb_model._get_module_category_id(data["category"])
        author_ids = mb_model._get_author_ids(tuple(data["authors"]))
        maintainer_ids = mb_model._get_maintainer_ids(tuple(data["maintainers"]))
        dev_status_id = mb_model._get_dev_status_id(data["development_status"])
        dependency_ids = mb_model._get_dependency_ids(
            repository_branch, data["depends"]
        )
        external_dependencies = data["external_dependencies"]
        python_dependency_ids = mb_model._get_python_dependency_ids(
            tuple(external_dependencies.get("python", []))
        )
        license_id = mb_model._get_license_id(data["license"])
        values = {
            "repository_branch_id": repository_branch.id,
            "branch_id": repository_branch.branch_id.id,
            "module_id": module.id,
            "title": data["title"],
            "summary": data["summary"],
            "category_id": category_id,
            "author_ids": [(6, 0, author_ids)],
            "maintainer_ids": [(6, 0, maintainer_ids)],
            "dependency_ids": [(6, 0, dependency_ids)],
            "external_dependencies": external_dependencies,
            "python_dependency_ids": [(6, 0, python_dependency_ids)],
            "license_id": license_id,
            "version": data["version"],
            "development_status_id": dev_status_id,
            "installable": data["installable"],
            "auto_install": data["auto_install"],
            "application": data["application"],
            "is_standard": data["is_standard"],
            "is_enterprise": data["is_enterprise"],
            "is_community": data["is_community"],
            "sloc_python": data["sloc_python"],
            "sloc_xml": data["sloc_xml"],
            "sloc_js": data["sloc_js"],
            "sloc_css": data["sloc_css"],
            "last_scanned_commit": data["last_scanned_commit"],
            "pr_url": data["pr_url"],
        }
        return values

    def _create_or_update_module_branch(self, values):
        mb_model = self.env["odoo.module.branch"]
        rec = mb_model.search(
            [
                ("module_id", "=", values["module_id"]),
                # Module could have been already created to satisfy dependencies
                # (without 'repository_branch_id' set)
                "|",
                ("repository_branch_id", "=", values["repository_branch_id"]),
                ("branch_id", "=", values["branch_id"]),
            ],
            limit=1,
        )
        if rec:
            rec.sudo().write(values)
        else:
            rec = mb_model.sudo().create(values)
        return rec

    @tools.ormcache("name")
    def _get_repository_org(self, name):
        rec = self.env["odoo.repository.org"].search([("name", "=", name)], limit=1)
        if not rec:
            rec = self.env["odoo.repository.org"].sudo().create({"name": name})
        return rec

    @tools.ormcache("org_id", "name")
    def _get_repository(self, org_id, name, data):
        rec = self.env["odoo.repository"].search(
            [
                ("org_id", "=", org_id),
                ("name", "=", name),
            ],
            limit=1,
        )
        values = {
            "org_id": org_id,
            "name": name,
            "repo_url": data["repo_url"],
            "repo_type": data["repo_type"],
            "active": data["active"],
        }
        if rec:
            rec.sudo().write(values)
        else:
            rec = self.env["odoo.repository"].sudo().create(values)
        return rec

    @tools.ormcache("org_id", "repository_id", "branch_id")
    def _get_repository_branch(self, org_id, repository_id, branch_id, data):
        rec = self.env["odoo.repository.branch"].search(
            [
                ("repository_id", "=", repository_id),
                ("branch_id", "=", branch_id),
            ],
            limit=1,
        )
        values = {
            "repository_id": repository_id,
            "branch_id": branch_id,
            "last_scanned_commit": data["last_scanned_commit"],
        }
        if rec:
            rec.sudo().write(values)
        else:
            rec = self.env["odoo.repository.branch"].sudo().create(values)
        return rec
