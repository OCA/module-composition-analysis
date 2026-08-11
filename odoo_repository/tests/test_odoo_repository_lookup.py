# Copyright 2026 ACSONE SA/NV (<https://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from .common import Common


class TestOdooRepositoryLookup(Common):
    def setUp(self):
        super().setUp()
        self.repository_model = self.env["odoo.repository"]

    # -- _parse_clone_url --------------------------------------------------

    def test_parse_clone_url_https(self):
        self.assertEqual(
            self.repository_model._parse_clone_url(
                "https://github.com/acsone/account-invoicing.git"
            ),
            ("github.com", "acsone", "account-invoicing"),
        )

    def test_parse_clone_url_without_git_suffix(self):
        self.assertEqual(
            self.repository_model._parse_clone_url(
                "https://github.com/OCA/account-invoicing"
            ),
            ("github.com", "OCA", "account-invoicing"),
        )

    def test_parse_clone_url_scp_syntax(self):
        self.assertEqual(
            self.repository_model._parse_clone_url(
                "git@github.com:acsone/account-invoicing.git"
            ),
            ("github.com", "acsone", "account-invoicing"),
        )

    def test_parse_clone_url_nested_namespace(self):
        """GitLab sub-groups are kept as part of the organization."""
        self.assertEqual(
            self.repository_model._parse_clone_url(
                "https://gitlab.com/acsone/odoo/addons.git"
            ),
            ("gitlab.com", "acsone/odoo", "addons"),
        )

    def test_parse_clone_url_invalid(self):
        for url in (None, "", "not-an-url", "https://github.com/lonely-segment"):
            with self.subTest(url=url):
                self.assertEqual(
                    self.repository_model._parse_clone_url(url), (None, None, None)
                )

    # -- organization sequence ---------------------------------------------

    def _create_repository(self, org_name, repo_name, **values):
        org = self.env["odoo.repository.org"].search([("name", "=", org_name)])
        if not org:
            org = self.env["odoo.repository.org"].create({"name": org_name})
        vals = {
            "org_id": org.id,
            "name": repo_name,
            "repo_url": f"https://github.com/{org_name}/{repo_name}",
            "clone_url": f"https://github.com/{org_name}/{repo_name}.git",
            "repo_type": "github",
        }
        vals.update(values)
        return self.env["odoo.repository"].create(vals)

    def test_find_module_branch_honours_org_sequence(self):
        """A module shared by several organizations resolves to the first one."""
        module = self._create_odoo_module("account_invoice_triple_discount")
        module_branches = {}
        for org_name, sequence in (("OCA", 10), ("acsone", 20)):
            repository = self._create_repository(org_name, "account-invoicing")
            repository.org_id.sequence = sequence
            repository_branch = self._create_odoo_repository_branch(
                repository, self.branch
            )
            module_branches[org_name] = self._create_odoo_module_branch(
                module,
                self.branch,
                repository_branch_id=repository_branch.id,
                specific=False,
            )
        module_branch_model = self.env["odoo.module.branch"]
        found = module_branch_model._find(self.branch, module, repo=False)
        self.assertEqual(found, module_branches["OCA"])
        # Reversing the priority of the organizations reverses the result
        module_branches["acsone"].repository_id.org_id.sequence = 1
        found = module_branch_model._find(self.branch, module, repo=False)
        self.assertEqual(found, module_branches["acsone"])
