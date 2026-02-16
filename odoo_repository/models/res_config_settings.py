# Copyright 2023 Camptocamp SA
# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    config_odoo_repository_storage_path = fields.Char(
        string="Storage local path", config_parameter="odoo_repository_storage_path"
    )
    config_odoo_repository_workaround_fs_errors = fields.Boolean(
        related="company_id.config_odoo_repository_workaround_fs_errors",
        readonly=False,
    )
    config_odoo_repository_default_token_id = fields.Many2one(
        related="company_id.config_odoo_repository_default_token_id",
        readonly=False,
    )
    config_odoo_repository_main_node_url = fields.Char(
        string="Endpoint URL", config_parameter="odoo_repository_main_node_url"
    )
    config_odoo_repository_oca_blacklist = fields.Char(
        string="OCA Repository Blacklist",
        config_parameter="odoo_repository.oca_repo_blacklist",
        help=(
            "Comma-separated list of OCA repositories to skip during synchronization. "
            "Example: OCB,OpenUpgrade"
        ),
    )
