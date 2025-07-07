# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
{
    "name": "Odoo Project Stats",
    "summary": "Get some stats about your Odoo Projects.",
    "version": "16.0.1.0.0",
    "category": "Tools",
    "author": "Camptocamp, Odoo Community Association (OCA)",
    "website": "https://github.com/camptocamp/odoo-repository",
    "data": [
        "security/ir.model.access.csv",
        "data/odoo_project_stat_config.xml",
        "views/odoo_project.xml",
        "views/odoo_project_stat_config.xml",
    ],
    "installable": True,
    "depends": [
        "odoo_project",
        # OCA/web
        "web_widget_plotly_chart",
    ],
    "license": "AGPL-3",
}
