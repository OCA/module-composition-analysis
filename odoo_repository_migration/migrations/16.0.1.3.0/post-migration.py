# Copyright 2025 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    migrate_odoo_module_branch_timelines(env)


def migrate_odoo_module_branch_timelines(env):
    _logger.info("Migrate Odoo module timelines to 'odoo.module.branch.timeline'...")
    query = """
        SELECT id, next_odoo_version_state, next_odoo_version_module_id
        FROM odoo_module_branch
        WHERE next_odoo_version_state != 'same';
    """
    env.cr.execute(query)
    rows = env.cr.dictfetchall()
    vals_list = []
    for row in rows:
        vals = {
            "module_branch_id": row["id"],
            "state": row["next_odoo_version_state"],
            "next_module_id": row["next_odoo_version_module_id"],
        }
        vals_list.append(vals)
    env["odoo.module.branch.timeline"].create(vals_list)
