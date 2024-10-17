# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    recompute_migration_scan(env)


def recompute_migration_scan(env):
    _logger.info("Recompute '<odoo.module.branch>.migration_scan' field...")
    mods = env["odoo.module.branch"].search([])
    mods.modified(["last_scanned_commit"])
    mods.flush_recordset(["migration_scan"])
