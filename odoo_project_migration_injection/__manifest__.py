# Copyright 2025 Raphaël Reverdy <raphael.reverdy@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
{
    "name": "Odoo Project Migration Injection",
    "summary": "Inject modules during project migrations.",
    "version": "16.0.1.0.0",
    "category": "Tools",
    "author": "Akretion, Odoo Community Association (OCA)",
    "website": "https://github.com/camptocamp/odoo-repository",
    "data": [
        "views/odoo_project.xml",
    ],
    "installable": True,
    "depends": [
        "odoo_project_migration",
    ],
    "license": "AGPL-3",
}
