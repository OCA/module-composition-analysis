# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooRepositoryAddonsPath(models.Model):
    _name = "odoo.repository.addons_path"
    _description = "Addons"

    relative_path = fields.Char(required=True)
    is_standard = fields.Boolean(
        string="Standard?",
        help="Does this folder contain modules from Odoo S.A.?",
        default=False,
    )
    is_enterprise = fields.Boolean(
        string="Enterprise?",
        help=(
            "Does this folder contain Enterprise modules?\n"
            "(from Odoo S.A., a contributor or your organization)"
        ),
        default=False,
    )
    is_community = fields.Boolean(
        string="Community Contribution?",
        help=(
            "Does this folder contain Odoo generic community modules?\n"
            "(from OCA, a contributor or your organization)"
        ),
        default=False,
    )

    _sql_constraints = [
        (
            "addons_path_uniq",
            "UNIQUE (relative_path, is_standard, is_enterprise, is_community)",
            "This addons-path already exists.",
        ),
    ]
