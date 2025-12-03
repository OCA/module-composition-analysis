This module collects and records modules migration data from Odoo
repositories.

Thanks to [oca-port](https://github.com/OCA/oca-port/) and data
collected by `odoo_repository`, this module will generate migration data
on each module for declared migration paths (e.g. 16.0 -> 18.0).

Also, for specific cases you can declare what a module became in a given
Odoo version, like OCA `web_domain_field` replaced by standard Odoo module
`web` starting from 17.0 (with an optional explanation that could help
users, like how to use this new module compared to the previous one).

Given a migration path, a module can get one of this migration status:

| Status | Description |
| ------ | ----------- |
| *Fully Ported* | All commits from source version are present in target version |
| *To migrate*   | The module doesn't exist on target version |
| *Ported (missing commits?)* | Some commits from source version are not ported in target version (could be false-positive) |
| *To review* | A migration PR has been detected |
| *Replaced* | The module has been replaced by another one (not sharing the same git history) |
| *Moved to standard?* | The module name has been detected in Odoo standard repositories for target version. High chance this module is or should be replaced by another one instead (by creating a timeline), so it mainly helps to detect such cases. |
| *Moved to OCA* | the module name is available in an OCA repository (could be a false-positive because sharing the same name, in such case a timeline has to be created) |
| *Moved to generic repo* | a specific module (only available in a project) in source version now exists in a generic repository (could be a false-positive if both modules have only their name in common) |

It helps to build a consolidated knowledge database accross different
Odoo versions for everyone: functionals and developers.
