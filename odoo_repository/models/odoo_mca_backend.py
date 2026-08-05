# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class OdooMCABackend(models.Model):
    """Backend collection for Odoo MCA system.

    This backend is used as the collection for all MCA-related components.
    """

    _name = "odoo.mca.backend"
    _inherit = "collection.base"
    _description = "Odoo MCA Backend"

    name = fields.Char(required=True)
