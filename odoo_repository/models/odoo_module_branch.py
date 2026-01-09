# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import pathlib
import random
import time
from urllib.parse import urlparse

from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError
from odoo.osv import expression

from odoo.addons.queue_job.exception import RetryableJobError

from ..utils import github
from ..utils.module import adapt_version


class OdooModuleBranch(models.Model):
    _name = "odoo.module.branch"
    _description = "Odoo Module Branch"
    _order = "repository_sequence, module_name, branch_name"

    module_id = fields.Many2one(
        comodel_name="odoo.module",
        ondelete="restrict",
        string="Technical name",
        required=True,
        index=True,
    )
    module_name = fields.Char(
        string="Module Technical Name", related="module_id.name", store=True, index=True
    )
    repository_branch_id = fields.Many2one(
        comodel_name="odoo.repository.branch",
        ondelete="set null",
        string="Repository Branch",
        index=True,
    )
    repository_id = fields.Many2one(
        related="repository_branch_id.repository_id",
        store=True,
        index=True,
        precompute=True,
        string="Repository",
    )
    repository_sequence = fields.Integer(
        related="repository_id.sequence",
        store=True,
        index=True,
    )
    org_id = fields.Many2one(
        related="repository_branch_id.repository_id.org_id",
        store=True,
        string="Organization",
    )
    branch_id = fields.Many2one(
        # NOTE: not a related on 'repository_branch_id' as we need to create
        # modules without knowing in advance what is their repo (orphaned modules).
        comodel_name="odoo.branch",
        ondelete="cascade",
        string="Odoo Version",
        required=True,
        index=True,
    )
    branch_name = fields.Char(
        string="Branch Name", related="branch_id.name", store=True, index=True
    )
    branch_sequence = fields.Integer(
        string="Branch Sequence", related="branch_id.sequence", store=True, index=True
    )
    pr_url = fields.Char(string="PR URL")
    is_standard = fields.Boolean(
        string="Standard?",
        help="Is this module part of Odoo standard?",
        default=False,
    )
    is_enterprise = fields.Boolean(
        string="Enterprise?",
        help="Is this module designed for Odoo Enterprise only?",
        default=False,
    )
    is_community = fields.Boolean(
        string="Community?",
        help="Is this module a contribution of the community?",
        default=False,
    )
    title = fields.Char(index=True, help="Descriptive name")
    name = fields.Char(
        string="Techname",
        compute="_compute_name",
        store=True,
        index=True,
    )
    summary = fields.Char(index=True)
    category_id = fields.Many2one(
        comodel_name="odoo.module.category",
        ondelete="restrict",
        string="Category",
        index=True,
    )
    author_ids = fields.Many2many(
        comodel_name="odoo.author",
        string="Authors",
    )
    maintainer_ids = fields.Many2many(
        comodel_name="odoo.maintainer",
        relation="module_branch_maintainer_rel",
        column1="module_branch_id",
        column2="maintainer_id",
        string="Maintainers",
    )
    dependency_ids = fields.Many2many(
        comodel_name="odoo.module.branch",
        relation="module_branch_dependency_rel",
        column1="module_branch_id",
        column2="dependency_id",
        string="Dependencies",
    )
    reverse_dependency_ids = fields.Many2many(
        comodel_name="odoo.module.branch",
        relation="module_branch_dependency_rel",
        column1="dependency_id",
        column2="module_branch_id",
        string="Reverse Dependencies",
    )
    global_dependency_level = fields.Integer(
        compute="_compute_dependency_level",
        recursive=True,
        store=True,
        string="Global Dep. Level",
        help="Dependency level including all standard Odoo modules.",
    )
    non_std_dependency_level = fields.Integer(
        compute="_compute_dependency_level",
        recursive=True,
        store=True,
        string="Non-Std Dep. Level",
        help="Dependency level excluding all standard Odoo modules.",
    )
    license_id = fields.Many2one(
        comodel_name="odoo.license",
        ondelete="restrict",
        string="License",
        index=True,
    )
    version = fields.Char("Last version")
    version_ids = fields.One2many(
        comodel_name="odoo.module.branch.version",
        inverse_name="module_branch_id",
        string="Versions",
    )
    development_status_id = fields.Many2one(
        comodel_name="odoo.module.dev.status",
        ondelete="restrict",
        string="Develoment Status",
        index=True,
    )
    external_dependencies = fields.Serialized()
    python_dependency_ids = fields.Many2many(
        comodel_name="odoo.python.dependency",
        string="Python Dependencies",
    )
    application = fields.Boolean(default=False)
    installable = fields.Boolean(default=True)
    auto_install = fields.Boolean(
        string="Auto-Install",
        default=False,
    )
    sloc_python = fields.Integer("Python", help="Python source lines of code")
    sloc_xml = fields.Integer("XML", help="XML source lines of code")
    sloc_js = fields.Integer("JS", help="JavaScript source lines of code")
    sloc_css = fields.Integer("CSS", help="CSS source lines of code")
    last_scanned_commit = fields.Char()
    removed = fields.Boolean()
    addons_path = fields.Char(
        help="Technical field. Where the module is located in the repository."
    )
    full_path = fields.Char(compute="_compute_full_path")
    url = fields.Char("URL", compute="_compute_url")
    specific = fields.Boolean(
        help=(
            "Module specific to a project repository."
            "It cannot be used across different projects."
        )
    )

    _sql_constraints = [
        (
            "module_id_branch_id_repository_id_uniq",
            "UNIQUE (module_id, branch_id, repository_id)",
            "This module already exists for this repository/branch.",
        ),
    ]

    def init(self):
        # Index to complete unique constraint 'module_id_branch_id_repository_id_uniq'.
        # This is mandatory to support repository_id=NULL in the constraint,
        # so we cannot create the same orphaned module twice.
        indexes = [
            # PostgreSQL < 15 (partial indexes)
            """
                CREATE UNIQUE INDEX IF NOT EXISTS odoo_module_branch_uniq_not_null
                ON odoo_module_branch (module_id, branch_id, repository_id)
                WHERE repository_id IS NOT NULL;
            """,
            """
                CREATE UNIQUE INDEX IF NOT EXISTS odoo_module_branch_uniq_null
                ON odoo_module_branch (module_id, branch_id)
                WHERE repository_id IS NULL;
            """
            # PostgreSQL >= 15 (with NULLS NOT DISTINCT)
            # """
            #     CREATE UNIQUE INDEX odoo_module_branch_uniq
            #     ON odoo_module_branch (module_id, branch_id, repository_id)
            #     NULLS NOT DISTINCT;
            # """
        ]
        for index in indexes:
            self._cr.execute(index)

    @api.constrains("specific", "dependency_ids")
    def _check_generic_depends_on_specific(self):
        for rec in self:
            if not rec.specific:
                specific_deps = rec.dependency_ids.filtered("specific")
                if specific_deps:
                    msg = _(
                        "Generic module %(generic_mod)s cannot depend "
                        "on specific module(s): %(specific_mods)s"
                    )
                    raise ValidationError(
                        msg
                        % {
                            "generic_mod": rec.module_name,
                            "specific_mods": ", ".join(
                                specific_deps.mapped("module_name")
                            ),
                        }
                    )

    @api.depends("module_name", "addons_path")
    def _compute_full_path(self):
        for rec in self:
            rec.full_path = pathlib.Path(rec.addons_path or ".").joinpath(
                rec.module_name
            )

    @api.depends(
        "repository_id.repo_url",
        "branch_name",
        "repository_branch_id.cloned_branch",
        "addons_path",
        "module_name",
    )
    def _compute_url(self):
        for rec in self:
            rec.url = False
            if not rec.repository_id:
                continue
            branch = rec.branch_name
            if rec.repository_branch_id.cloned_branch:
                branch = rec.repository_branch_id.cloned_branch
            module_path = "/".join([rec.addons_path or ".", rec.module_name])
            rec.url = rec.repository_id._get_resource_url(branch, module_path)

    @api.depends("repository_branch_id.name", "module_id.name")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.repository_branch_id.name or '?'} - {rec.module_id.name}"

    @api.depends(
        "dependency_ids.global_dependency_level",
        "dependency_ids.non_std_dependency_level",
        "dependency_ids.is_standard",
    )
    def _compute_dependency_level(self):
        for rec in self:
            global_max_parent_level = max(
                [dep.global_dependency_level for dep in rec.dependency_ids] + [0]
            )
            rec.global_dependency_level = global_max_parent_level + 1
            non_std_max_parent_level = max(
                [
                    dep.non_std_dependency_level
                    for dep in rec.dependency_ids
                    if not dep.is_standard
                ]
                + [0]
            )
            rec.non_std_dependency_level = (
                # Set 0 on all std modules so they will always have a dependency
                # level inferior to non-std modules
                (non_std_max_parent_level + 1)
                if not rec.is_standard
                else 0
            )

    def _get_recursive_dependencies(self, domain=None):
        """Return all dependencies recursively.

        A domain can be applied to restrict the modules to return, e.g:

        >>> mod._get_recursive_dependencies([("org_id", "=", "OCA")])

        """
        if not domain:
            domain = []
        dependencies = self.dependency_ids.filtered_domain(domain)
        dep_ids = set(dependencies.ids)
        for dep in dependencies:
            dep_ids |= set(
                dep._get_recursive_dependencies().filtered_domain(domain).ids
            )
        return self.browse(dep_ids)

    def open_recursive_dependencies(self):
        self.ensure_one()
        xml_id = "odoo_repository.odoo_module_branch_action_recursive_dependencies"
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        action["name"] = "All dependencies"
        action["domain"] = [("id", "in", self._get_recursive_dependencies().ids)]
        return action

    def action_find_pr_url(self):
        """Find the PR on GitHub that adds this module."""
        self.ensure_one()
        if self.pr_url or self.repository_branch_id or self.specific:
            return False
        values = {"pr_url": False}
        pr_urls = self._find_pr_urls_from_github(self.branch_id, self.module_id)
        for pr_url in pr_urls:
            values["pr_url"] = pr_url
            # Get the relevant repository from PR URL if not yet defined
            if not self.repository_branch_id:
                repository = self._find_repository_from_pr_url(pr_url)
                if not repository:
                    continue
                repository_branch = self.env["odoo.repository.branch"].search(
                    [
                        ("repository_id", "=", repository.id),
                        ("branch_id", "=", self.branch_id.id),
                    ]
                )
                if repository_branch:
                    values["repository_branch_id"] = repository_branch.id
                    break
        self.sudo().write(values)
        return True

    def _find_pr_urls_from_github(self, branch, module):
        """Find the GitHub Pull Requests adding `module` on `branch`."""
        # Look for an open PR first, then unmerged (which includes closed ones)
        for pr_state in ("open", "unmerged"):
            url = (
                f"search/issues?q=is:pr+is:{pr_state}+base:{branch.name}"
                f"+in:title+{module.name}"
            )
            try:
                # Mitigate 'API rate limit exceeded' GitHub API error
                # by adding a random waiting time of 1-4s
                time.sleep(random.randrange(1, 5))
                prs = github.request(self.env, url)
            except RuntimeError as exc:
                raise RetryableJobError("Error while looking for PR URL") from exc
            for pr in prs.get("items", []):
                yield pr["html_url"]

    def _find_repository_from_pr_url(self, pr_url):
        """Return the repository corresponding to `pr_url`."""
        # Extract organization and repository name from PR url
        path_parts = list(filter(None, urlparse(pr_url).path.split("/")))
        org, repository = path_parts[:2]
        repository_model = self.env["odoo.repository"].with_context(active_test=False)
        return repository_model.search(
            [
                ("org_id", "=", org),
                ("name", "=", repository),
            ]
        )

    @api.model
    @api.returns("odoo.module.branch")
    def push_scanned_data(self, repo_branch_id, module, data):
        """Entry point for the scanner to push its data."""
        module = self._get_module(module)
        repo_branch = self.env["odoo.repository.branch"].browse(repo_branch_id)
        values = self._prepare_module_branch_values(repo_branch, module, data)
        return self._create_or_update(repo_branch, module, values)

    def _prepare_module_branch_values(self, repo_branch, module, data):
        # Get existing module.branch (hosted in scanned repo) if any
        module_branch = self._get_module_branch(
            repo_branch.branch_id, module, repo=repo_branch.repository_id
        )
        # Prepare the 'odoo.module.branch' values
        manifest = data.get("manifest", {})
        values = {
            "repository_branch_id": repo_branch.id,
            "branch_id": repo_branch.branch_id.id,
            "module_id": module.id,
            "is_standard": data["is_standard"],
            "is_enterprise": data["is_enterprise"],
            "is_community": data["is_community"],
            "last_scanned_commit": data.get("last_scanned_commit", False),
            "addons_path": data["relative_path"],
            "specific": repo_branch.repository_id.specific,
            # Unset PR URL once the module is available in the repository.
            "pr_url": False,
        }
        if manifest:
            category_id = self._get_module_category_id(manifest.get("category", ""))
            author_ids = self._get_author_ids(manifest.get("author", ""))
            maintainer_ids = self._get_maintainer_ids(
                tuple(manifest.get("maintainers", []))
            )
            dev_status_id = self._get_dev_status_id(
                manifest.get("development_status", "")
            )
            dependency_ids = []
            external_dependencies = {}
            python_dependency_ids = []
            if manifest.get("installable", True):
                dependency_ids = self._get_dependency_ids(
                    repo_branch,
                    # Set at least a dependency on "base" if not defined
                    manifest.get("depends") or ["base"],
                )
                external_dependencies = manifest.get("external_dependencies", {})
                python_dependency_ids = self._get_python_dependency_ids(
                    tuple(external_dependencies.get("python", []))
                )
            license_id = self._get_license_id(manifest.get("license", ""))
            values.update(
                {
                    "title": manifest.get("name", False),
                    "summary": manifest.get(
                        "summary", manifest.get("description", False)
                    ),
                    "category_id": category_id,
                    "author_ids": [(6, 0, author_ids)],
                    "maintainer_ids": [(6, 0, maintainer_ids)],
                    "dependency_ids": [(6, 0, dependency_ids)],
                    "external_dependencies": external_dependencies,
                    "python_dependency_ids": [(6, 0, python_dependency_ids)],
                    "license_id": license_id,
                    "version": manifest.get("version", False),
                    "development_status_id": dev_status_id,
                    "application": manifest.get("application", False),
                    "installable": manifest.get("installable", True),
                    "auto_install": manifest.get("auto_install", False),
                }
            )
        if data.get("last_scanned_commit"):
            values.update(
                {
                    "removed": False,
                    "sloc_python": data["code"]["Python"],
                    "sloc_xml": data["code"]["XML"],
                    "sloc_js": data["code"]["JavaScript"],
                    "sloc_css": data["code"]["CSS"],
                }
            )
        # Handle module removal
        elif module_branch:
            values.update(
                {
                    "installable": False,
                    "removed": True,
                }
            )
        # Handle versions history
        if values.get("installable"):
            versions = self._prepare_module_branch_version_ids_values(
                repo_branch,
                module_branch,
                module,
                # If no history versions was scanned (could happen if versions are
                # part of an unfetched branch), create one corresponding to the
                # current manifest version if any but without commit.
                versions=(
                    data.get("versions")
                    or (
                        {values["version"]: {"commit": None}}
                        if values.get("version")
                        else {}
                    )
                ),
            )
            if versions:
                values["version_ids"] = versions
        return values

    def _create_or_update(self, repo_branch, module, values):
        """Create or update a `odoo.module.branch` record from scanned module.

        This method will try to link/update an existing module in DB, that could be:
            - already scanned in the current repository (simple update)
            - orphaned (update the repository of such module)
            - unmerged/pending (only if the scanned repository hosts generic modules)
        """
        branch = repo_branch.branch_id
        module_branch = False
        module_branch_in_repo = self._get_module_branch(
            branch, module, repo=repo_branch.repository_id
        )
        # Module was already scanned in the current repository: update it
        if module_branch_in_repo:
            module_branch = module_branch_in_repo
        # Module was never scanned in the current repository:
        else:
            # Check if an orphaned module exists
            orphaned_module_branch = self._get_orphaned_module_branch(branch, module)
            if orphaned_module_branch:
                module_branch = orphaned_module_branch
            # Check if an unmerged module exists if the scanned repo is generic
            elif not repo_branch.repository_id.specific:
                unmerged_module_branch = self._get_unmerged_module_branch(
                    branch, module
                )
                if unmerged_module_branch:
                    module_branch = unmerged_module_branch
        module_branch = self._filter_module_to_update(repo_branch, module_branch)
        if module_branch:
            values["repository_branch_id"] = repo_branch.id
            module_branch.sudo().write(values)
        else:
            module_branch = self.sudo().create(values)
            # Special case: when creating 'base' module, ensure that all previously
            # scanned modules without dependency for the same Odoo version get
            # a dependency against this 'base' module.
            if module_branch.module_name == "base":
                module_branch._update_modules_to_depend_on_base()
        return module_branch

    @api.model
    def _update_modules_to_depend_on_base(self):
        """Make all scanned modules without dependency depending on 'base'.

        It is executed when a 'base' module is scanned for the first time.
        """
        # Update only scanned modules (ones found in repositories)
        all_modules = self.search(
            [
                ("dependency_ids", "=", False),
                ("last_scanned_commit", "!=", False),
                ("branch_id", "!=", False),
                ("module_name", "!=", "base"),
            ],
        )
        for branch, modules in tools.groupby(all_modules, key=lambda m: m.branch_id):
            base = self.search(
                [("module_name", "=", "base"), ("branch_id", "=", branch.id)],
                limit=1,
            )
            if not base:
                continue
            self.union(*modules).dependency_ids |= base

    def _filter_module_to_update(self, repo_branch, module_branch):
        """Hook called by '_create_or_update'.

        Can be overriden to return `False` to force the creation of a new
        `odoo.module.branch` record linked to the scanned repository.
        """
        return module_branch

    @api.model
    def _get_existing_version(self, module, manifest_value, commit):
        if not commit:
            return self.env["odoo.module.branch.version"]
        return self.env["odoo.module.branch.version"].search(
            [
                ("module_name", "=", module.name),
                ("manifest_value", "=", manifest_value),
                ("commit", "=", commit),
            ],
            limit=1,
        )

    def _prepare_module_branch_version_ids_values(
        self, repo_branch, module_branch, module, versions
    ):
        # Insert new versions
        version_ids = []
        other_odoo_versions = (
            self.env["odoo.branch"]._get_all_odoo_versions() - repo_branch.branch_id
        )
        for manifest_value, data in versions.items():
            # Version scanned doesn't belong to the current branch, skipping
            if any(
                manifest_value.startswith(odoo_version.name + ".")
                for odoo_version in other_odoo_versions
            ):
                continue
            name = adapt_version(repo_branch.branch_id.name, manifest_value)
            # As we could import versions history from previous Odoo releases
            # (i.e. the branch has been started from a previous one), check if
            # it hasn't been imported already thanks to the related commit SHA
            version = self._get_existing_version(module, manifest_value, data["commit"])
            if version and module_branch:
                # Skip if the version has already been imported for a
                # previous Odoo release
                if version.branch_id.sequence < module_branch.branch_id.sequence:
                    continue
                # Corner case: we scanned a version that was already imported
                # through a newer Odoo branch. Downgrade the existing version
                # to the current module branch.
                if version.branch_id.sequence > module_branch.branch_id.sequence:
                    version.write(
                        {
                            "module_branch_id": module_branch.id,
                            "name": name,
                        }
                    )
                    continue
            module_version = module_branch.version_ids.filtered(
                lambda v: v.name == name and v.manifest_value == manifest_value
            )
            values = {
                "name": name,
                "manifest_value": manifest_value,
                "commit": data["commit"],
                "has_migration_script": data.get("migration_script", False),
            }
            if module_version:
                version_ids.append(fields.Command.update(module_version.id, values))
            else:
                version_ids.append(fields.Command.create(values))
        return version_ids

    @tools.ormcache("category_name")
    def _get_module_category_id(self, category_name):
        if category_name:
            rec = self.env["odoo.module.category"].search(
                [("name", "=", category_name)], limit=1
            )
            if not rec:
                rec = (
                    self.env["odoo.module.category"]
                    .sudo()
                    .create({"name": category_name})
                )
            return rec.id
        return False

    @tools.ormcache("names")
    def _get_author_ids(self, names):
        if names:
            # Some Odoo std modules have a list instead of a string as 'author'
            if isinstance(names, str):
                names = [name.strip() for name in names.split(",")]
            authors = self.env["odoo.author"].search([("name", "in", names)])
            missing_author_names = set(names) - set(authors.mapped("name"))
            missing_authors = self.env["odoo.author"]
            if missing_author_names:
                missing_authors = (
                    self.env["odoo.author"]
                    .sudo()
                    .create([{"name": name} for name in missing_author_names])
                )
            return (authors | missing_authors).ids
        return []

    @tools.ormcache("names")
    def _get_maintainer_ids(self, names):
        if names:
            maintainers = self.env["odoo.maintainer"].search([("name", "in", names)])
            missing_maintainer_names = set(names) - set(maintainers.mapped("name"))
            created = self.env["odoo.maintainer"]
            if missing_maintainer_names:
                created = created.sudo().create(
                    [{"name": name} for name in missing_maintainer_names]
                )
            return (maintainers | created).ids
        return []

    @tools.ormcache("name")
    def _get_dev_status_id(self, name):
        if name:
            rec = self.env["odoo.module.dev.status"].search(
                [("name", "=", name)], limit=1
            )
            if not rec:
                rec = self.env["odoo.module.dev.status"].sudo().create({"name": name})
            return rec.id
        return False

    @api.model
    def _find(self, branch, module, repo, domain=None):
        """Find an `odoo.module.branch` record matching parameters.

        The lookup of the module is in this order:
            - search in `repo`
            - search among generic modules in other repositories
            - search among orphaned modules

        Additional search criteria can be added with `domain`,
        e.g. `domain=[('installable', '=', True)]`.
        """
        # Look for the module first in the current repository
        module_branch = self.browse()
        if repo:
            module_branch = self._get_module_branch(
                branch, module, repo=repo, domain=domain
            )
        # Then look among generic modules
        if not module_branch:
            modules_branch = self._get_module_branch(
                branch,
                module,
                domain=expression.AND(
                    [
                        domain or [],
                        [("specific", "=", False), ("repository_id", "!=", False)],
                    ],
                ),
            )
            module_branch = fields.first(modules_branch)
        # Otherwise look for the module among orphaned modules
        if not module_branch:
            module_branch = self._get_orphaned_module_branch(
                branch, module, domain=domain
            )
        return module_branch

    @api.model
    def _find_or_create(self, branch, module, repo, domain=None):
        """Find an `odoo.module.branch` record (see `_find`), or create an orphaned one."""
        module_branch = self._find(branch, module, repo, domain=domain)
        # If still not found, create the module as an orphaned module
        # (it will hopefully be bound to a repository later)
        if not module_branch:
            module_branch = self.sudo()._create_orphaned_module_branch(branch, module)
        return module_branch

    def _get_dependency_ids(self, repo_branch, depends: list):
        dependency_ids = []
        for depend in depends:
            module = self._get_module(depend)
            dependency = self._find_or_create(
                repo_branch.branch_id, module, repo_branch.repository_id
            )
            dependency_ids.append(dependency.id)
        return dependency_ids

    @tools.ormcache("packages")
    def _get_python_dependency_ids(self, packages):
        if packages:
            dependencies = self.env["odoo.python.dependency"].search(
                [("name", "in", packages)]
            )
            missing_dependencies = set(packages) - set(dependencies.mapped("name"))
            created = self.env["odoo.python.dependency"]
            if missing_dependencies:
                created = created.sudo().create(
                    [{"name": package} for package in missing_dependencies]
                )
            return (dependencies | created).ids
        return []

    @tools.ormcache("license_name")
    def _get_license_id(self, license_name):
        if license_name:
            license_model = self.env["odoo.license"]
            rec = license_model.search([("name", "=", license_name)], limit=1)
            if not rec:
                rec = license_model.sudo().create({"name": license_name})
            return rec.id
        return False

    def _get_module(self, name):
        module = self.env["odoo.module"].search([("name", "=", name)])
        if not module:
            module = self.env["odoo.module"].sudo().create({"name": name})
        return module

    @api.model
    def _get_module_branch_domain(self, branch, module, repo=None, domain=None):
        """Return the domain to identify an `odoo.module.branch` record."""
        _domain = [
            ("branch_id", "=", branch.id),
            ("module_id", "=", module.id),
        ]
        if repo:
            _domain.append(("repository_id", "=", repo.id))
        elif repo is False:
            _domain.append(("repository_id", "=", False))
        if domain:
            _domain.extend(domain)
        return _domain

    @api.model
    def _get_module_branch(self, branch, module, repo=None, domain=None):
        """Return the `odoo.module.branch` if it already exists. Do not create it."""
        domain = self._get_module_branch_domain(
            branch, module, repo=repo, domain=domain
        )
        return self.search(domain)

    @api.model
    def _get_orphaned_module_branch_domain(self, branch, module, domain=None):
        """Return the domain to identify an orphaned module (without repo)."""
        return self._get_module_branch_domain(branch, module, repo=False, domain=domain)

    @api.model
    def _get_orphaned_module_branch(self, branch, module, domain=None):
        """Return an orphaned module matching `branch` and `module`."""
        domain = self._get_orphaned_module_branch_domain(branch, module, domain=domain)
        return self.search(domain)

    @api.model
    def _get_unmerged_module_branch_domain(self, branch, module):
        """Return the domain to identify an unmerged module (coming from a PR)."""
        domain = self._get_module_branch_domain(branch, module)
        domain.extend(
            [
                ("specific", "=", False),
                ("repository_id", "!=", False),
                ("pr_url", "!=", False),
            ]
        )
        return domain

    @api.model
    def _get_unmerged_module_branch(self, branch, module):
        """Return an unmerged module matching `branch` and `module`."""
        domain = self._get_unmerged_module_branch_domain(branch, module)
        return self.search(domain)

    def _create_orphaned_module_branch(self, branch, module):
        """Create an orphaned module."""
        values = {
            "module_id": module.id,
            "branch_id": branch.id,
        }
        return self.create(values)

    # TODO adds ormcache
    def _get_modules_data(self, orgs=None, repositories=None, branches=None):
        """Returns modules data matching the criteria.

        E.g.:

            >>> self._get_modules_data(
            ...     orgs=['OCA'],
            ...     repositories=['server-env'],
            ...     branches=['15.0', '16.0'],
            ... )

        """
        domain = self._get_modules_domain(orgs, repositories, branches)
        modules = self.search(domain)
        data = []
        for module in modules:
            data.append(module._to_dict())
        return data

    def _get_modules_domain(self, orgs=None, repositories=None, branches=None):
        domain = [
            # Do not return orphans modules
            ("org_id", "!=", False),
            ("repository_id", "!=", False),
            ("branch_id", "!=", False),
        ]
        if orgs:
            domain.append(("org_id", "in", orgs))
        if repositories:
            domain.append(("repository_id", "in", repositories))
        if branches:
            domain.append(("branch_id", "in", branches))
        return domain

    def _to_dict(self):
        """Convert module data to a dictionary."""
        self.ensure_one()
        return {
            "module": self.module_name,
            "branch": self.branch_id.name,
            "repository": self.repository_branch_id._to_dict(),
            "title": self.title,
            "summary": self.summary,
            "authors": self.author_ids.mapped("name"),
            "maintainers": self.maintainer_ids.mapped("name"),
            "depends": self.dependency_ids.mapped("module_name"),
            "category": self.category_id.name,
            "license": self.license_id.name,
            "version": self.version,
            "versions": [version._to_dict() for version in self.version_ids],
            "development_status": self.development_status_id.name,
            "application": self.application,
            "installable": self.installable,
            "auto_install": self.auto_install,
            "external_dependencies": self.external_dependencies,
            "is_standard": self.is_standard,
            "is_enterprise": self.is_enterprise,
            "is_community": self.is_community,
            "sloc_python": self.sloc_python,
            "sloc_xml": self.sloc_xml,
            "sloc_js": self.sloc_js,
            "sloc_css": self.sloc_css,
            "last_scanned_commit": self.last_scanned_commit,
            "addons_path": self.addons_path,
            "pr_url": self.pr_url,
        }
