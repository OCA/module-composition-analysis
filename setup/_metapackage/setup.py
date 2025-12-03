import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo-addons-oca-odoo-repository",
    description="Meta package for oca-odoo-repository Odoo addons",
    version=version,
    install_requires=[
        'odoo-addon-odoo_project>=16.0dev,<16.1dev',
        'odoo-addon-odoo_project_changelog>=16.0dev,<16.1dev',
        'odoo-addon-odoo_project_migration>=16.0dev,<16.1dev',
        'odoo-addon-odoo_project_stat>=16.0dev,<16.1dev',
        'odoo-addon-odoo_repository>=16.0dev,<16.1dev',
        'odoo-addon-odoo_repository_migration>=16.0dev,<16.1dev',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
        'Framework :: Odoo :: 16.0',
    ]
)
