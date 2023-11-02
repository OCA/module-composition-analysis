# Copyright 2023 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
{
    "name": "Odoo Repositories Data",
    "summary": "Base module to host data collected from Odoo repositories.",
    "version": "16.0.1.0.0",
    "category": "Tools",
    "author": "Camptocamp, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/TODO",
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "data/odoo_repository_org.xml",
        "data/odoo_repository_addons_path.xml",
        "data/odoo_repository.xml",
        "data/odoo.repository.csv",
        "data/queue_job.xml",
        "views/menu.xml",
        "views/ssh_key.xml",
        "views/odoo_author.xml",
        "views/odoo_branch.xml",
        "views/odoo_license.xml",
        "views/odoo_maintainer.xml",
        "views/odoo_module.xml",
        "views/odoo_module_branch.xml",
        "views/odoo_module_category.xml",
        "views/odoo_module_dev_status.xml",
        "views/odoo_python_dependency.xml",
        "views/odoo_repository.xml",
        "views/odoo_repository_addons_path.xml",
        "views/odoo_repository_branch.xml",
        "views/odoo_repository_org.xml",
        "views/res_config_settings.xml",
    ],
    "installable": True,
    "application": True,
    "depends": [
        # core
        "base_sparse_field",
        # OCA/queue
        "queue_job",
    ],
    "external_dependencies": {
        "python": [
            "gitpython",
            "pygount",
            # TODO to publish
            # "odoo-addons-analyzer",
            # "odoo-repository-scanner"
        ],
    },
    "license": "AGPL-3",
}
