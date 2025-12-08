This module allows to generate CHANGELOGs for repositories used within a project.

Changelogs are generated from `git` commits history, and take as input source
and target references from this repository (a commit SHA, branch, tag...).
Only relevant changes done will be listed to not clutter the changelog
(translations, unit tests or documentation updates won't be listed).

The output is an HTML page where the user can easily navigate, fold and unfold sections.

 ![Changelog](./static/img/changelog.png)
