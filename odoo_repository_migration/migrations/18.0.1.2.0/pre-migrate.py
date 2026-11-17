# Copyright 2026  Akretion (https://www.akretion.com).
# @author Sébastien Alix <sebastien.alix@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

from openupgradelib import openupgrade  # noqa: F401

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    _rename_timeline_state_field(env)


def _rename_timeline_state_field(env):
    openupgrade.rename_fields(
        env,
        [
            (
                "odoo.module.branch.timeline",
                "odoo_module_branch_timeline",
                "state",
                "timeline_type",
            ),
        ],
    )
    _logger.info(
        "'state' field of 'odoo.module.branch.timeline' renamed to 'timeline_type'."
    )
