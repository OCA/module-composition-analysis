# Copyright 2026 Sébastien Alix
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

{
    "name": "Test",
    "version": "1.0.0",
    "category": "Test Module",
    "author": "Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/module-composition-analysis",
    "license": "AGPL-3",
    "depends": ["base"],
    "data": [
        "security/ir.model.access.csv",
        "views/my_model.xml",
    ],
    "demo": [
        "demo/my_model.xml",
    ],
    "installable": True,
}
