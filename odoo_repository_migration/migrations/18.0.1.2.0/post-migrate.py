# Copyright 2026  Akretion (https://www.akretion.com).
# @author Sébastien Alix <sebastien.alix@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    _confirm_existing_timelines(cr)


def _confirm_existing_timelines(cr):
    """Set existing timelines as confirmed."""
    count = openupgrade.logged_query(
        cr,
        "UPDATE odoo_module_branch_timeline SET state = 'confirmed'",
    )
    _logger.info(
        "%s existing 'odoo.module.branch.timeline' records set as confirmed.",
        count,
    )
