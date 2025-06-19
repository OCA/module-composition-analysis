This module allows to add (or remove) modules to a project migration.

Use cases:

1) Handle modules replacement

replace oca/storage:storage_backend (14.0) by oca/storage:fs_storage (18.0)

2) Remove modules in future version

Keep oca/web:web_responsive installed on 14.0 but do not install it in 18.0.


Usage:
In a project, tab "Migration", there is two fields: "Modules to add" and
"Module to remove". You have to specify in wich version the module will be added/removed.


