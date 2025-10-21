# Copyright 2025 Sebastien Alix <https://github.com/sebalix>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Odoo Repository Code",
    "summary": "Collect modules coding elements from Odoo Repositories.",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "author": "sebalix, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/module-composition-analysis",
    "data": [
        "security/ir.model.access.csv",
        "views/menu.xml",
        "views/odoo_model_version.xml",
        "views/odoo_module_branch_model.xml",
        "views/odoo_module_branch_model_field.xml",
        "views/odoo_module_branch_model_method.xml",
        "views/odoo_module_branch.xml",
    ],
    "installable": True,
    "depends": [
        "odoo_repository",
    ],
    "license": "AGPL-3",
}
