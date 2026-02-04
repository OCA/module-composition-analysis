# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.tests.common import TransactionCase

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
