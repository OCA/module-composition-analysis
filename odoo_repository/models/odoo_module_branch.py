# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class OdooModuleBranch(models.Model):
    _name = "odoo.module.branch"
    _description = "Odoo Module Branch"
    _order = "module_name, branch_name"

    module_id = fields.Many2one(
        comodel_name="odoo.module",
        ondelete="restrict",
        string="Technical name",
        required=True,
        index=True
    )
    module_name = fields.Char(
        string="Module Technical Name", related="module_id.name", store=True
    )
    repository_branch_id = fields.Many2one(
        comodel_name="odoo.repository.branch",
        ondelete="set null",
        string="Repository Branch",
        index=True
    )
    repository_id = fields.Many2one(
        related="repository_branch_id.repository_id",
        store=True,
        string="Repository",
    )
    org_id = fields.Many2one(
        related="repository_branch_id.repository_id.org_id",
        store=True,
        string="Organization",
    )
    branch_id = fields.Many2one(
        # NOTE: not a related on 'repository_branch_id' as we need to create
        # module dependencies without knowing in advance what is their repo.
        comodel_name="odoo.branch",
        ondelete="cascade",
        string="Branch",
        domain=[("odoo_version", "=", True)],
        required=True,
        index=True,
    )
    branch_name = fields.Char(
        string="Branch Name", related="branch_id.name", store=True
    )
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
    summary = fields.Char(string="Summary", index=True)
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
        column1="module_branch_id", column2="maintainer_id",
        string="Maintainers",
    )
    dependency_ids = fields.Many2many(
        comodel_name="odoo.module.branch",
        relation="module_branch_dependency_rel",
        column1="module_branch_id", column2="dependency_id",
        string="Dependencies",
    )
    reverse_dependency_ids = fields.Many2many(
        comodel_name="odoo.module.branch",
        relation="module_branch_dependency_rel",
        column1="dependency_id", column2="module_branch_id",
        string="Reverse Dependencies",
    )
    license_id = fields.Many2one(
        comodel_name="odoo.license",
        ondelete="restrict",
        string="License",
        index=True,
    )
    version = fields.Char(
        string="Version",
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
    application = fields.Boolean(
        string="Application",
        default=False,
    )
    installable = fields.Boolean(
        string="Installable",
        default=True,
    )
    auto_install = fields.Boolean(
        string="Auto-Install",
        default=False,
    )
    sloc_python = fields.Integer("Python", help="Python source lines of code")
    sloc_xml = fields.Integer("XML", help="XML source lines of code")
    sloc_js = fields.Integer("JS", help="JavaScript source lines of code")
    sloc_css = fields.Integer("CSS", help="CSS source lines of code")
    last_scanned_commit = fields.Char(string="Last Scanned Commit")

    _sql_constraints = [
        (
            "module_id_branch_id_uniq",
            "UNIQUE (module_id, branch_id)",
            "This module already exists for this branch."
        ),
    ]

    @api.depends("repository_branch_id.name", "module_id.name")
    def _compute_name(self):
        for rec in self:
            rec.name = (
                f"{rec.repository_branch_id.name or '?'} - {rec.module_id.name}"
            )

    @api.model
    @api.returns("odoo.module.branch")
    def push_scanned_data(self, repo_branch_id, module, data):
        """Entry point for the scanner to push its data."""
        manifest = data["manifest"]
        module = self._get_module(module)
        repo_branch = self.env["odoo.repository.branch"].browse(repo_branch_id)
        category_id = self._get_module_category_id(manifest.get("category", ""))
        author_ids = self._get_author_ids(manifest.get("author", ""))
        maintainer_ids = self._get_maintainer_ids(
            manifest.get("maintainers", [])
        )
        dev_status_id = self._get_dev_status_id(
            manifest.get("development_status", "")
        )
        dependency_ids = self._get_dependency_ids(
            repo_branch, manifest.get("depends", [])
        )
        python_dependency_ids = self._get_python_dependency_ids(
            manifest.get("external_dependencies", {}).get("python", [])
        )
        license_id = self._get_license_id(manifest.get("license", ""))
        values = {
            "repository_branch_id": repo_branch.id,
            "branch_id": repo_branch.branch_id.id,
            "module_id": module.id,
            "title": manifest.get("name", False),
            "summary": manifest.get(
                "summary", manifest.get("description", False)
            ),
            "category_id": category_id,
            "author_ids": [(6, 0, author_ids)],
            "maintainer_ids": [(6, 0, maintainer_ids)],
            "dependency_ids": [(6, 0, dependency_ids)],
            "python_dependency_ids": [(6, 0, python_dependency_ids)],
            "license_id": license_id,
            "version": manifest.get("version", False),
            "development_status_id": dev_status_id,
            "application": manifest.get("application", False),
            "installable": manifest.get("installable", True),
            "auto_install": manifest.get("auto_install", False),
            "is_standard": data["is_standard"],
            "is_enterprise": data["is_enterprise"],
            "is_community": data["is_community"],
            "sloc_python": data["code"]["Python"],
            "sloc_xml": data["code"]["XML"],
            "sloc_js": data["code"]["JavaScript"],
            "sloc_css": data["code"]["CSS"],
            "last_scanned_commit": data.get("last_scanned_commit", False)
        }
        return self._create_or_update(repo_branch, module, values)

    def _create_or_update(self, repo_branch, module, values):
        args = [
            ("branch_id", "=", repo_branch.branch_id.id),
            ("module_id", "=", module.id),
        ]
        module_branch = self.search(args)
        if module_branch:
            module_branch.sudo().write(values)
        else:
            module_branch = self.sudo().create(values)
        return module_branch

    def _get_module_category_id(self, category_name: str):
        if category_name:
            rec = self.env["odoo.module.category"].search(
                [("name", "=", category_name)], limit=1
            )
            if not rec:
                rec = self.env["odoo.module.category"].sudo().create(
                    {"name": category_name}
                )
            return rec.id
        return False

    def _get_author_ids(self, names: str):
        if names:
            # Some Odoo std modules have a list instead of a string as 'author'
            if not isinstance(names, list):
                names = [name.strip() for name in names.split(",")]
            authors = self.env["odoo.author"].search([("name", "in", names)])
            missing_author_names = set(names) - set(authors.mapped("name"))
            missing_authors = self.env["odoo.author"]
            if missing_author_names:
                missing_authors = self.env["odoo.author"].sudo().create(
                    [{"name": name} for name in missing_author_names]
                )
            return (authors | missing_authors).ids
        return []

    def _get_maintainer_ids(self, names: list):
        if names:
            maintainers = self.env["odoo.maintainer"].search(
                [("name", "in", names)]
            )
            missing_maintainer_names = (
                set(names) - set(maintainers.mapped("name"))
            )
            created = self.env["odoo.maintainer"]
            if missing_maintainer_names:
                created = created.sudo().create(
                    [{"name": name} for name in missing_maintainer_names]
                )
            return (maintainers | created).ids
        return []

    def _get_dev_status_id(self, name: str):
        if name:
            rec = self.env["odoo.module.dev.status"].search(
                [("name", "=", name)], limit=1
            )
            if not rec:
                rec = self.env["odoo.module.dev.status"].sudo().create(
                    {"name": name}
                )
            return rec.id
        return False

    def _get_dependency_ids(self, repo_branch, depends: list):
        dependency_ids = []
        for depend in depends:
            module = self._get_module(depend)
            dependency = self.search(
                [
                    ("module_id", "=", module.id),
                    ("branch_id", "=", repo_branch.branch_id.id),
                ]
            )
            if not dependency:
                dependency = self.sudo().create(
                    {
                        "module_id": module.id,
                        "branch_id": repo_branch.branch_id.id,
                    }
                )
            dependency_ids.append(dependency.id)
        return dependency_ids

    def _get_python_dependency_ids(self, packages: list):
        if packages:
            dependencies = self.env["odoo.python.dependency"].search(
                [("name", "in", packages)]
            )
            missing_dependencies = (
                set(packages) - set(dependencies.mapped("name"))
            )
            created = self.env["odoo.python.dependency"]
            if missing_dependencies:
                created = created.sudo().create(
                    [{"name": package} for package in missing_dependencies]
                )
            return (dependencies | created).ids
        return []

    def _get_license_id(self, license_name: str):
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
