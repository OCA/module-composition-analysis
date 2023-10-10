# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    config_odoo_repository_storage_path = fields.Char(
        string="Storage local path", config_parameter="odoo_repository_storage_path"
    )
    config_odoo_repository_github_token = fields.Char(
        string="GitHub Token", config_parameter="odoo_repository_github_token"
    )
    config_odoo_repository_main_node_url = fields.Char(
        string="Endpoint URL", config_parameter="odoo_repository_main_node_url"
    )
