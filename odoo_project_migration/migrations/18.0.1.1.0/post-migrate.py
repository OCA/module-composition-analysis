# Copyright 2026  Akretion (https://www.akretion.com).
# @author Sébastien Alix <sebastien.alix@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    recompute_timeline_project_migration_data(env)


def recompute_timeline_project_migration_data(env):
    """Recompute project migration data related to timelines."""
    timelines = env["odoo.module.branch.timeline"].search([])
    _logger.info(
        "Recompute project migration data related to %s timelines...", len(timelines)
    )
    timelines.migration_ids.force_update()
    timelines.project_migration_ids.force_update()
