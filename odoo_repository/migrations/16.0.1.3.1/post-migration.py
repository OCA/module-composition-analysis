# Copyright 2025 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    update_modules_to_depend_on_base(env)


def update_modules_to_depend_on_base(env):
    _logger.info("Update modules without dependencies to depend on 'base'...")
    env["odoo.module.branch"]._update_modules_to_depend_on_base()
