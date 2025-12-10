# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import json
import logging
import os
import pathlib
from urllib.parse import urljoin

import requests

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError
from odoo.osv.expression import AND, OR

from odoo.addons.queue_job.delay import chain
from odoo.addons.queue_job.exception import RetryableJobError
from odoo.addons.queue_job.job import identity_exact

from ..utils.scanner import RepositoryScannerOdooEnv

_logger = logging.getLogger(__name__)


class OdooRepository(models.Model):
    _name = "odoo.repository"
    _description = "Odoo Modules Repository"
    _order = "sequence, display_name"

    _repositories_path_key = "odoo_repository_storage_path"

    display_name = fields.Char(compute="_compute_display_name", store=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=100)
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
    clone_name = fields.Char(
        help=(
            "Force the name of the cloned repository (folder on disk). "
            "If not set, the name of the repository will be used."
        ),
    )
    repo_type = fields.Selection(
        selection=[
            ("github", "GitHub"),
            ("gitlab", "GitLab"),
        ],
    )
    ssh_key_id = fields.Many2one(
        comodel_name="ssh.key",
        ondelete="restrict",
        string="SSH Key",
        help="SSH key used to clone/fetch this repository.",
    )
    token_id = fields.Many2one(
        comodel_name="authentication.token",
        ondelete="restrict",
        string="Token",
        help="Token used to clone/fetch this repository.",
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
    )
    scan_weekday_ids = fields.Many2many(
        comodel_name="time.weekday",
        string="Scanning days",
        help=(
            "Limit scanning of this repository by the scheduled action to "
            "certain days only. If not defined, the scan will happen every day."
        ),
    )
    manual_branches = fields.Boolean(
        string="Configure branches manually",
        help=(
            "By default repository branches follows the configured Odoo versions "
            "(e.g: 17.0, 18.0...). Enable this option to configure your own branches."
        ),
    )
    specific = fields.Boolean(
        help=(
            "Host specific modules (that are not generic). "
            "Used for project repositories."
        ),
    )
    module_ids = fields.One2many(
        comodel_name="odoo.module.branch",
        inverse_name="repository_id",
        string="Modules",
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
            "org_id_name_uniq",
            "UNIQUE (org_id, name)",
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

    def _get_odoo_branches_to_scan(self):
        self.ensure_one()
        if self.manual_branches:
            return self.branch_ids.branch_id
        return self.env["odoo.branch"]._get_all_odoo_versions(active_test=True)

    def _cron_scanner_domain(self):
        today = fields.Date.today()
        weekday = today.weekday()
        return AND(
            [
                [("to_scan", "=", True)],
                OR(
                    [
                        [("scan_weekday_ids.name", "=", weekday)],
                        [("scan_weekday_ids", "=", False)],
                    ]
                ),
            ]
        )

    @api.model
    def cron_scanner(self, branches=None, force=False):
        """Scan and collect Odoo repositories data.

        As the scanner is run on the same server than Odoo, a special class
        `RepositoryScannerOdooEnv` is used so the scanner can request Odoo
        through an environment (api.Environment).

        `branches` parameter allows to filter the `odoo.branch` to take into
        account for the scan, e.g. `branches=["16.0", "18.0"]`.
        """
        repositories = self.search(self._cron_scanner_domain())
        branches_ = self.env["odoo.branch"]._get_all_odoo_versions(active_test=True)
        if branches:
            branches_ = branches_.filtered(lambda br: br.name in branches)
        for repo in repositories:
            repo.action_scan(branch_ids=branches_.ids, force=force, raise_exc=False)

    def _check_config(self):
        # Check the configuration of repositories folder
        key = self._repositories_path_key
        repositories_path = self.env["ir.config_parameter"].sudo().get_param(key, "")
        if not repositories_path:
            raise UserError(
                _(
                    "Please define the '{key}' system parameter to "
                    "clone repositories in the folder of your choice.".format(key=key)
                )
            )
        # Ensure the folder exists
        pathlib.Path(repositories_path).mkdir(parents=True, exist_ok=True)

    def _check_existing_jobs(self, raise_exc=True):
        """Check if a scan is already triggered for this repository."""
        self.ensure_one()
        existing_job = (
            self.env["queue.job"]
            .sudo()
            .search(
                [
                    ("model_name", "=", self._name),
                    ("records", "ilike", f'%"ids": [{self.id}]%'),
                    (
                        "state",
                        "in",
                        [
                            "wait_dependencies",
                            "pending",
                            "enqueued",
                            "started",
                        ],
                    ),
                ],
                limit=1,
            )
        )
        if existing_job:
            msg = _("A scan is already ongoing for repository %s") % self.display_name
            if raise_exc:
                raise UserError(msg)
            _logger.warning(msg)
            return True
        return False

    def action_scan(self, branch_ids=None, force=False, raise_exc=True):
        """Scan the whole repository."""
        self._check_config()
        for rec in self:
            if not rec.to_scan:
                continue
            if rec._check_existing_jobs(raise_exc=raise_exc):
                continue
            # Get branch records to scan
            branches = rec._get_odoo_branches_to_scan()
            if branch_ids:
                branches = branches & self.env["odoo.branch"].search(
                    [("id", "in", branch_ids)]
                )
            if not branches:
                continue
            # Create a list of tuples ({odoo_version}, {branch_name})
            versions_branches = [(branch.name, branch.name) for branch in branches]
            if rec.manual_branches:
                versions_branches = [
                    (rb.branch_id.name, rb.cloned_branch or rb.branch_id.name)
                    for rb in rec.branch_ids
                    if rb.branch_id in branches
                ]
            if force:
                rec._reset_scanned_commits(branch_ids=branch_ids)
            # Scan repository branches sequentially as they need to be checked out
            # to perform the analysis
            # Here the launched job is responsible to:
            #   1) detect modules updated on the first branch
            #   2) spawn jobs to scan each module on that branch
            #   3) spawn a job to update the last scanned commit of the repo/branch
            #   4) spawn the next job responsible to detect modules updated
            #      on the next branch
            version_branch = versions_branches[0]
            next_versions_branches = versions_branches[1:]
            job = rec._create_job_detect_modules_to_scan_on_branch(
                version_branch, next_versions_branches, versions_branches
            )
            job.delay()
        return True

    def _create_job_detect_modules_to_scan_on_branch(
        self, version_branch, next_versions_branches, all_versions_branches
    ):
        self.ensure_one()
        version, branch = version_branch
        branch_str = branch
        if version != branch:
            branch_str = f"{branch} ({version})"
        delayable = self.delayable(
            description=f"Detect modules to scan in {self.display_name}#{branch_str}",
            identity_key=identity_exact,
        )
        return delayable._detect_modules_to_scan_on_branch(
            version_branch, next_versions_branches, all_versions_branches
        )

    def _detect_modules_to_scan_on_branch(
        self, version_branch, next_versions_branches, all_versions_branches
    ):
        """Detect the modules to scan on `branch`.

        It will spawn a job for each module to scan, and two other jobs to:
            - update the last scanned commit on the repo/branch
            - scan the next branch (so each branch is scanned in cascade)

        This ensure to scan different branches sequentially for a given repository.
        """
        version, branch = version_branch
        try:
            # Get the list of modules updated since last scan
            params = self._prepare_scanner_parameters(version, branch)
            scanner = RepositoryScannerOdooEnv(**params)
            data = scanner.detect_modules_to_scan()
            # Prepare all subsequent jobs based on modules to scan
            jobs = self._create_subsequent_jobs(
                version_branch, next_versions_branches, all_versions_branches, data
            )
            # Chain them  altogether
            if jobs:
                chain(*jobs).delay()
        except Exception as exc:
            raise RetryableJobError("Scanner error") from exc

    def _create_subsequent_jobs(
        self, version_branch, next_versions_branches, all_versions_branches, data
    ):
        jobs = []
        version, branch = version_branch
        # Spawn one job per module to scan
        for data_ in data.get("addons_paths", {}).values():
            for module_path in data_["modules_to_scan"]:
                job = self._create_job_scan_module_on_branch(
                    version, branch, module_path, data_["specs"]
                )
                jobs.append(job)
        # + another one to update the last scanned commit of the repository
        if data.get("repo_branch_id"):
            job = self._create_job_update_last_scanned_commit(
                data["repo_branch_id"],
                data["last_fetched_commit"],
            )
            jobs.append(job)
        # + another one to detect modules to scan on the next branch
        version_branch = next_versions_branches and next_versions_branches[0]
        next_versions_branches = next_versions_branches[1:]
        if version_branch:
            jobs.append(
                self._create_job_detect_modules_to_scan_on_branch(
                    version_branch, next_versions_branches, all_versions_branches
                )
            )
        return jobs

    def _create_job_scan_module_on_branch(self, version, branch, module_path, specs):
        self.ensure_one()
        branch_str = branch
        if version != branch:
            branch_str = f"{branch} ({version})"
        delayable = self.delayable(
            description=f"Scan {self.display_name}#{branch_str} - {module_path}",
            identity_key=identity_exact,
        )
        return delayable._scan_module_on_branch(version, branch, module_path, specs)

    def _scan_module_on_branch(self, version, branch, module_path, specs):
        """Scan `module_path` from `branch`."""
        try:
            params = self._prepare_scanner_parameters(version, branch)
            scanner = RepositoryScannerOdooEnv(**params)
            return scanner.scan_module(module_path, specs)
        except Exception as exc:
            raise RetryableJobError("Scanner error") from exc

    def _create_job_update_last_scanned_commit(
        self, repo_branch_id, last_scanned_commit, last_scan=False
    ):
        self.ensure_one()
        repo_branch_model = self.env["odoo.repository.branch"]
        repo_branch = repo_branch_model.browse(repo_branch_id).exists()
        delayable = repo_branch.delayable(
            description=f"Update last scanned commit of {repo_branch.display_name}",
            identity_key=identity_exact,
        )
        return delayable._update_last_scanned_commit(last_scanned_commit)

    def _reset_scanned_commits(self, branch_ids=None):
        """Reset the scanned commits.

        This will make the next repository scan restarting from the beginning,
        and thus making it slower.
        """
        self.ensure_one()
        if branch_ids is None:
            branch_ids = self.branch_ids.branch_id.ids
        repo_branches = self.branch_ids.filtered(
            lambda rb: rb.branch_id.id in branch_ids
        )
        repo_branches.write({"last_scanned_commit": False})
        repo_branches.module_ids.sudo().write({"last_scanned_commit": False})

    def _get_token(self):
        """Return the first available token found for this repository.

        It will check the available tokens in this order:
            - specific token linked to this repository
            - default token defined in the global settings
            - token defined through an environment variable
        """
        self.ensure_one()
        return (
            self.token_id.token
            or self.env.company.config_odoo_repository_default_token_id.token
            or os.environ.get("GITHUB_TOKEN")
        )

    def _prepare_scanner_parameters(self, version, branch):
        ir_config = self.env["ir.config_parameter"]
        repositories_path = ir_config.sudo().get_param(self._repositories_path_key)
        return {
            "org": self.org_id.name,
            "name": self.name,
            "clone_url": self.clone_url,
            "version": version,
            "branch": branch,
            "addons_paths_data": self.addons_path_ids.read(
                [
                    "relative_path",
                    "is_standard",
                    "is_enterprise",
                    "is_community",
                ]
            ),
            "repositories_path": repositories_path,
            "repo_type": self.repo_type,
            "ssh_key": self.ssh_key_id.private_key,
            "token": self._get_token(),
            "workaround_fs_errors": (
                self.env.company.config_odoo_repository_workaround_fs_errors
            ),
            "clone_name": self.clone_name,
            "env": self.env,
        }

    def action_force_scan(self, branch_ids=None, raise_exc=True):
        """Force the scan of the repositories.

        It will restart the scan without considering the last scanned commit,
        overriding already collected module data if any.
        """
        self.ensure_one()
        return self.action_scan(branch_ids=branch_ids, force=True, raise_exc=raise_exc)

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
        branch_domain = []
        if branches:
            branch_domain.append(("name", "in", branches))
        branches = self.env["odoo.branch"].search(branch_domain)
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
            self._create_or_update_module_branch(values, module_data)

    def _prepare_module_branch_values(self, data):
        # Get branch, repository and technical module
        branch = self.env["odoo.branch"].search([("name", "=", data["branch"])])
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
        versions_values = self._prepare_version_ids_values(
            repository_branch, module, data["versions"]
        )
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
            "version_ids": versions_values,
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

    def _prepare_version_ids_values(self, repo_branch, module, versions: list[dict]):
        version_ids = []
        for version in versions:
            version_model = self.env["odoo.module.branch.version"]
            rec = version_model.search(
                [
                    ("module_branch_id.branch_id", "=", repo_branch.branch_id.id),
                    ("module_branch_id.module_id", "=", module.id),
                    ("name", "=", version["name"]),
                ],
                limit=1,
            )
            if rec:
                version_ids.append(fields.Command.update(rec.id, version))
            else:
                version_ids.append(fields.Command.create(version))
        return version_ids

    def _create_or_update_module_branch(self, values, raw_data):
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
        values = self._pre_create_or_update_module_branch(rec, values, raw_data)
        if rec:
            rec.sudo().write(values)
        else:
            rec = mb_model.sudo().create(values)
        self._post_create_or_update_module_branch(rec, values, raw_data)
        return rec

    def _pre_create_or_update_module_branch(self, rec, values, raw_data):
        """Hook executed before the creation or update of `rec`. Return values."""
        return values

    def _post_create_or_update_module_branch(self, rec, values, raw_data):
        """Hook executed after the creation or update of `rec`."""

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

    def _get_resource_url(self, branch, path):
        self.ensure_one()
        # NOTE: GitHub and GitLab supports the same URL pattern
        url = "/".join(["tree", branch, path])
        return urljoin(self.repo_url + "/", url)

    def unlink(self):
        # There is no deletion on cascade policy by default, but for specific
        # repositories we want to remove specific modules anyway.
        # This will also avoid to raise UNIQUE constraint
        # 'odoo_module_branch_uniq_null(module_id, branch_id)' if module names
        # are shared between repositories.
        for rec in self:
            if rec.specific:
                rec.branch_ids.module_ids.sudo().unlink()
        return super().unlink()

    def open_modules(self):
        self.ensure_one()
        xml_id = "odoo_repository.odoo_module_branch_action"
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        action["domain"] = [("repository_id", "=", self.id)]
        action["context"] = {"search_default_installable": True}
        if len(self.module_ids.branch_id) > 1:
            action["context"]["search_default_group_by_branch_id"] = True
        return action
