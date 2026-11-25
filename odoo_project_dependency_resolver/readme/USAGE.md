On the project, set *Dependency Management* to *Resolved*, pick the format of
the dependency file and, if it is not at the root of the repository under its
usual name, adjust its path.

There is nothing else to declare. A dependency file only holds packaged
addons, so the modules of a resolved project are the union of three sources:

- the addons of the dependency file, with the versions it pins;
- the modules hosted by the project repository, which are the code of the
  project itself and are shipped with it rather than installed as a package;
- their missing dependencies, pulled from the dependency graph, which is
  where Odoo standard modules come from.

*Additional Modules* is there for what none of the three reaches, Odoo
Enterprise modules typically.

The modules are refreshed at each scan, and by the *Resolve Dependencies*
button. Whatever the resolution could not do is reported on the project, in
the *Resolution Log* field.

## What a scan does

Scanning a resolved project only scans the repository of the project: the
repositories its modules come from are derived from the dependency file, so
none of them is known before that file has been read.

The resolution is chained to that scan, so it reads a file that has just been
fetched, and it then spawns the scan of the repositories it discovered. A
second resolution runs once they have all been scanned, completing what the
first one could not know: the modules of a repository that had never been
scanned, and the dependency graph the resolved modules are walked through.

Note that the second resolution waits for the detection of the modules to
scan in every repository, not for every module to have been scanned: the
scanner spawns the latter as it goes. A module scanned late is therefore
accounted for by the next scan of the project.

## Modules pinned on a fork

A module frozen on a commit of a fork, such as:

    odoo-addon-account-invoice-triple-discount @
        git+https://github.com/acsone/account-invoicing.git@3e4c54b
        #subdirectory=setup/account_invoice_triple_discount

is not treated as a new module. It stays attached to the module of the
repository the fork originates from, so that dependencies, migration scripts
and changelogs keep working, and the fork is recorded on the project module as
*Installed From*. Its version is read from the manifest at the pinned revision.

A module added by a pull request not merged yet is a special case: it exists
in no repository known to Odoo MCA, so it stays an orphaned module and shows
up among the unknown modules of the project. *Installed From* is then the only
way to reach a repository from it, and the *Fork Of* of that fork tells where
the module is heading.
