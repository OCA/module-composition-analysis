# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class SSHKey(models.Model):
    _name = "ssh.key"
    _description = "SSH private key"

    name = fields.Char(required=True)
    private_key = fields.Text(required=True, help="SSH private key without passphrase.")
