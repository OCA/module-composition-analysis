A fork is registered on the fly, whenever something looks up the repository a
clone URL points at and GitHub answers that it is a fork of a repository
already known.

It can be created by hand too, by setting *Fork Of* on a repository. Either
way, a fork is never scanned: it hosts the very same modules as the repository
it comes from, and a second scanned repository holding them would make the
module of a dependency ambiguous for every project. A constraint enforces it.

Its credentials remain editable though, and they are what reading a private
fork needs. The forks of a repository are listed on it.
