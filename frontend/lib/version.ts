// Single source of truth for the "A.R.C. Framework vX.YY" string that
// appears in the footer of every /about/* page. Before this file the
// version was hardcoded nine separate times; two of those had already
// drifted to v7.14 while commit history had moved on to v7.38, and hand-
// fixing the stragglers one page at a time would only guarantee a tenth
// drifts next. Bump this one line when the framework version changes —
// nothing else should ever hardcode the string again.
//
// Not read from package.json: that file's "version" field tracks the npm
// package (0.1.0) and has never tracked this "vX.YY" scheme, which comes
// from the version prefix on release commit messages (e.g. "v7.38 —
// PDF/docx/odt publish support..."). There is no other machine-readable
// source for it.
export const ARC_FRAMEWORK_VERSION = 'v7.38';
