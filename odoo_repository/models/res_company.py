# Copyright 2024 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    config_odoo_repository_default_token_id = fields.Many2one(
        comodel_name="authentication.token",
        string="Default token",
        help="Default token used to clone repositories and authenticate on API like GitHub.",
    )
    config_odoo_repository_workaround_fs_errors = fields.Boolean(
        string="Workaround FS errors",
        help=(
            "Fix file system permissions when cloning repositories. "
            "Errors could be triggered on some file systems when git tries to "
            "execute 'chown' commands on its internal configuration files. "
            "This option will workaround this issue."
        ),
    )
