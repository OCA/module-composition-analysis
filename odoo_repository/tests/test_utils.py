# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import time
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.odoo_repository.utils.github import _get_retry_after
from odoo.addons.odoo_repository.utils.module import adapt_version


class TestUtils(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

    def test_adapt_version(self):
        # Module version equals major version: add prefix
        self.assertEqual(adapt_version("14.0", "14.0"), "14.0.14.0")
        # Basic module version: add prefix
        self.assertEqual(adapt_version("14.0", "1.0.0"), "14.0.1.0.0")
        # Module version already prefixed with major version
        self.assertEqual(adapt_version("14.0", "14.0.1.0.0"), "14.0.1.0.0")
        # Dot chars added as prefix or suffix in the provided version
        self.assertEqual(adapt_version("14.0", ".1.0.0"), "14.0.1.0.0")
        self.assertEqual(adapt_version("14.0", "1.0.0."), "14.0.1.0.0")
        self.assertEqual(adapt_version("14.0", "...1.0.0..."), "14.0.1.0.0")

    def _response(self, status_code, headers=None, text=""):
        response = mock.Mock()
        response.status_code = status_code
        response.headers = headers or {}
        response.text = text
        return response

    def test_get_retry_after(self):
        # Not a rate limit status code
        self.assertIsNone(_get_retry_after(self._response(404)))
        self.assertIsNone(_get_retry_after(self._response(403)))
        # Secondary rate limit with Retry-After header
        response = self._response(429, headers={"Retry-After": "120"})
        self.assertEqual(_get_retry_after(response), 120)
        # Primary rate limit with reset timestamp
        response = self._response(
            403,
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + 600),
            },
        )
        self.assertAlmostEqual(_get_retry_after(response), 600, delta=5)
        # Reset timestamp in the past: wait at least 60s
        response = self._response(
            403,
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "0"},
        )
        self.assertEqual(_get_retry_after(response), 60)
        # Rate limit detected only through the response body
        response = self._response(403, text="API rate limit exceeded for ...")
        self.assertEqual(_get_retry_after(response), 60)
