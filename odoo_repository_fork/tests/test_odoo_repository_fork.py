# Copyright 2026 ACSONE SA/NV (<https://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tools import mute_logger

from odoo.addons.odoo_repository.tests.common import Common

GITHUB_REQUEST = (
    "odoo.addons.odoo_repository_fork.models.odoo_repository.github.request"
)


class TestOdooRepositoryFork(Common):
    def setUp(self):
        super().setUp()
        # '_fetch_github_fork_parents' is an ormcache, make sure a test never
        # observes what a previous one stored.
        self.env.registry.clear_cache()
        self.repository_model = self.env["odoo.repository"]

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
        if values.get("upstream_repository_id"):
            vals["to_scan"] = False
        vals.update(values)
        return self.env["odoo.repository"].create(vals)

    def test_find_upstream_known_repository(self):
        """A URL pointing to a known repository resolves without calling GitHub."""
        repository = self._create_repository("OCA", "account-invoicing")
        with patch(GITHUB_REQUEST) as request:
            found = self.repository_model._find_upstream_repository(
                "https://github.com/OCA/account-invoicing.git"
            )
        self.assertEqual(found, repository)
        request.assert_not_called()

    def test_find_upstream_from_github_fork(self):
        """An unknown fork resolves to the repository it originates from."""
        upstream = self._create_repository("OCA", "account-invoicing")
        payload = {
            "fork": True,
            "parent": {"full_name": "OCA/account-invoicing"},
            "source": {"full_name": "OCA/account-invoicing"},
        }
        with patch(GITHUB_REQUEST, return_value=payload) as request:
            found = self.repository_model._find_upstream_repository(
                "https://github.com/acsone/account-invoicing.git"
            )
        self.assertEqual(found, upstream)
        request.assert_called_once()
        self.assertIn("repos/acsone/account-invoicing", request.call_args[0])

    def test_find_upstream_prefers_parent_over_source(self):
        """On a fork chain, the closest known ancestor wins."""
        self._create_repository("OCA", "account-invoicing")
        intermediate = self._create_repository("camptocamp", "account-invoicing")
        payload = {
            "fork": True,
            "parent": {"full_name": "camptocamp/account-invoicing"},
            "source": {"full_name": "OCA/account-invoicing"},
        }
        with patch(GITHUB_REQUEST, return_value=payload):
            found = self.repository_model._find_upstream_repository(
                "https://github.com/acsone/account-invoicing.git"
            )
        self.assertEqual(found, intermediate)

    def test_find_upstream_falls_back_to_source(self):
        """An unknown intermediate fork does not hide the root of the chain."""
        root = self._create_repository("OCA", "account-invoicing")
        payload = {
            "fork": True,
            "parent": {"full_name": "unknown-org/account-invoicing"},
            "source": {"full_name": "OCA/account-invoicing"},
        }
        with patch(GITHUB_REQUEST, return_value=payload):
            found = self.repository_model._find_upstream_repository(
                "https://github.com/acsone/account-invoicing.git"
            )
        self.assertEqual(found, root)

    def test_find_upstream_not_a_fork(self):
        """A standalone repository has no upstream to resolve."""
        self._create_repository("OCA", "account-invoicing")
        with patch(GITHUB_REQUEST, return_value={"fork": False}):
            found = self.repository_model._find_upstream_repository(
                "https://github.com/acsone/vendored-addons.git"
            )
        self.assertFalse(found)

    def test_find_upstream_non_github_host(self):
        """Only GitHub exposes the fork ancestry: no API call is attempted."""
        with patch(GITHUB_REQUEST) as request:
            found = self.repository_model._find_upstream_repository(
                "https://gitlab.com/acsone/account-invoicing.git"
            )
        self.assertFalse(found)
        request.assert_not_called()

    def test_find_upstream_github_error_is_not_cached(self):
        """A GitHub outage degrades gracefully and does not poison the cache."""
        upstream = self._create_repository("OCA", "account-invoicing")
        url = "https://github.com/acsone/account-invoicing.git"
        with (
            patch(GITHUB_REQUEST, side_effect=RuntimeError("API rate limit")),
            mute_logger("odoo.addons.odoo_repository_fork.models.odoo_repository"),
        ):
            self.assertFalse(self.repository_model._find_upstream_repository(url))
        payload = {
            "fork": True,
            "parent": {"full_name": "OCA/account-invoicing"},
            "source": {"full_name": "OCA/account-invoicing"},
        }
        with patch(GITHUB_REQUEST, return_value=payload):
            self.assertEqual(
                self.repository_model._find_upstream_repository(url), upstream
            )

    # -- registering a fork -------------------------------------------------

    def test_fork_is_registered_on_the_fly(self):
        """Discovering a fork documents it, so it can carry its credentials."""
        upstream = self._create_repository("OCA", "account-invoicing")
        payload = {
            "fork": True,
            "parent": {"full_name": "OCA/account-invoicing"},
            "source": {"full_name": "OCA/account-invoicing"},
        }
        url = "https://github.com/acsone/account-invoicing.git"
        with patch(GITHUB_REQUEST, return_value=payload):
            fork = self.repository_model._find_from_clone_url(url)
        self.assertEqual(fork.upstream_repository_id, upstream)
        self.assertEqual(fork.org_id.name, "acsone")
        self.assertEqual(fork.name, "account-invoicing")
        self.assertEqual(fork.clone_url, url)
        self.assertEqual(fork.repo_url, "https://github.com/acsone/account-invoicing")
        self.assertEqual(fork.repo_type, upstream.repo_type)
        # A fork hosts the modules of its origin, scanning it would duplicate them
        self.assertFalse(fork.to_scan)
        self.assertEqual(upstream.fork_ids, fork)

    def test_fork_is_registered_once(self):
        """A known fork is found by its URL, without asking GitHub again."""
        self._create_repository("OCA", "account-invoicing")
        payload = {
            "fork": True,
            "parent": {"full_name": "OCA/account-invoicing"},
            "source": {"full_name": "OCA/account-invoicing"},
        }
        url = "https://github.com/acsone/account-invoicing.git"
        with patch(GITHUB_REQUEST, return_value=payload):
            fork = self.repository_model._find_from_clone_url(url)
        with patch(GITHUB_REQUEST) as request:
            found = self.repository_model._find_from_clone_url(url)
        self.assertEqual(found, fork)
        request.assert_not_called()

    def test_fork_cannot_be_scanned(self):
        """Scanning a fork would make the module of a dependency ambiguous."""
        upstream = self._create_repository("OCA", "account-invoicing")
        fork = self._create_repository(
            "acsone", "account-invoicing", upstream_repository_id=upstream.id
        )
        self.assertFalse(fork.to_scan)
        with self.assertRaisesRegex(ValidationError, "cannot be scanned"):
            fork.to_scan = True

    def test_fork_cannot_be_its_own_upstream(self):
        repository = self._create_repository("OCA", "account-invoicing")
        with self.assertRaises(ValidationError):
            repository.upstream_repository_id = repository

    def test_fork_is_reached_with_its_own_credentials(self):
        """A private fork is read with the token registered on it."""
        upstream = self._create_repository("OCA", "account-invoicing")
        token = self.env["authentication.token"].create(
            {"name": "acsone", "token": "s3cr3t"}
        )
        fork = self._create_repository(
            "acsone",
            "account-invoicing",
            upstream_repository_id=upstream.id,
            token_id=token.id,
        )
        params = fork._prepare_base_scanner_parameters()
        self.assertEqual(params["org"], "acsone")
        self.assertEqual(params["token"], "s3cr3t")
        self.assertNotEqual(params["token"], upstream._get_token())
