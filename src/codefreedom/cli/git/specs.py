"""Inline specs attached to LLM requests for commit and PR generation.

These specs are bundled with the prompt so the model has the full
reference available offline — no URL lookups, no guessing. They
are formatted as "skills" the model can apply directly to the task.
"""

from __future__ import annotations


CONVENTIONAL_COMMITS_SPEC = """\
# Conventional Commits v1.0.0 (Inline Spec)

A lightweight convention on top of commit messages. It provides an easy
set of rules for creating an explicit commit history; which makes it
easier to write automated tools on top of.

## Commit message structure

<type>[optional scope][!]: <description>

[optional body]

[optional footer(s)]

## Rules

1. Commits MUST be prefixed with a type, which consists of a noun, e.g.
   ``feat``, ``fix``, followed by an OPTIONAL scope, OPTIONAL ``!`` for
   breaking changes, and a REQUIRED terminal colon and space.
2. The type ``feat`` MUST be used when a commit adds a new feature.
3. The type ``fix`` MUST be used when a commit represents a bug fix.
4. A scope MAY be provided after a type, in parenthesis, e.g.
   ``fix(parser):``.
5. A description MUST immediately follow the colon and space after the
   type/scope prefix. The description is a short summary of the code
   changes, e.g., ``fix: array parsing issue when an empty string found``.
6. A longer commit body MAY be provided after the short description.
7. A footer of one or more ``trailer: value`` lines MAY be provided
   after the body. ``BREAKING CHANGE: <description>`` is a special
   trailer that MUST be used when a commit introduces a breaking API
   change and the ``!`` shorthand is not used.
8. A ``!`` MAY be appended right before the colon to draw attention to
   breaking changes. If ``!`` is used, ``BREAKING CHANGE:`` MAY be
   omitted from the footer.
9. Types other than ``feat`` and ``fix`` MAY be used.
10. The units of information that make up Conventional Commits MUST
    NOT be treated as case sensitive by implementors, with the
    exception of ``BREAKING CHANGE`` which MUST be uppercase.

## Allowed types

- feat: A new feature for the user
- fix: A bug fix
- docs: Documentation only changes
- style: Changes that do not affect the meaning of the code
  (white-space, formatting, missing semi-colons, etc.)
- refactor: A code change that neither fixes a bug nor adds a feature
- perf: A code change that improves performance
- test: Adding missing tests or correcting existing tests
- build: Changes that affect the build system or external dependencies
  (npm, pip, brew, etc.)
- ci: Changes to CI configuration files and scripts
- chore: Other changes that don't modify src or test files
- revert: Reverts a previous commit

## Breaking changes

Indicated by appending ``!`` before the colon, e.g.:

    feat(api)!: drop legacy v1 endpoints

or by including ``BREAKING CHANGE:`` in the footer, e.g.:

    refactor(core): split transport into its own module

    BREAKING CHANGE: ``core.Transport`` was renamed to
    ``core.transport.Transport``.

## Reference examples (verbatim from the spec)

feat: allow provided config object to extend other configs
feat(lang): add Polish language support
fix: prevent racing of requests
fix(preprocessor): fix typo in README
docs: correct spelling of CHANGELOG
refactor: simplify share logic
perf: remove unnecessary string trim
test: ensure all internal methods return the correct type
build: add npm publish step
ci: add GitHub Actions workflow
chore: update grunt tasks
revert: feat(lang): add Polish language support
feat(api)!: drop support for Node 12
feat(api)!: send an email to the customer when a product is shipped

BREAKING CHANGE: environment variables now take precedence over config files
"""


PULL_REQUEST_GUIDE = """\
# Pull Request Guide (Inline Spec)

A great pull request makes code review fast and clear. Follow this spec
when generating PR title and body.

## Title

- Use Conventional Commits format: ``TYPE(SCOPE): DESCRIPTION``.
- Keep it under 72 characters.
- Use imperative mood ("add feature", not "added feature" or "adds").
- Lowercase first letter of the description; no trailing period.
- Capitalize the type word (lowercase by convention here).

## Body

A PR body should help reviewers understand the change. Use this structure
when generating the body (omit empty sections if not applicable):

### ## Summary
One or two sentences explaining what the PR does and why. Reference the
user-facing change, not the implementation detail.

### ## Changes
Bullet list of specific code changes. Group by file or area.
- src/foo/bar.py: add Baz class with do_thing() method
- src/foo/qux.py: refactor init to use new Baz

### ## Testing
How was this tested? What test cases were added or changed? Include
manual verification steps when relevant.

### ## Related issues
Link related issues using ``Fixes #123``, ``Closes #456``, or
``Refs #789``.

## Example title (good)

    feat(auth): add OAuth2 login support

## Example title (bad)

    Update auth.py with new OAuth flow
    ^^^^^                                 No conventional type
    WIP                                   Not ready for review
    fix                                                        <-- missing scope and description
    feat(auth): add OAuth2 login support with PKCE and refresh token rotation and 10 other things
    ^^^^^^ Too long; will wrap in the GitHub UI

## Example body (good)

    ## Summary
    Adds OAuth2 login so users can sign in with their Google account.
    The new flow is enabled by setting ``OAUTH_GOOGLE_CLIENT_ID`` and
    ``OAUTH_GOOGLE_SECRET`` in the env.

    ## Changes
    - Add ``/api/v1/auth/oauth/google`` endpoint that handles the OAuth2
      callback and exchanges the auth code for an access token.
    - Refactor ``auth.middleware`` to delegate to a provider registry
      so multiple OAuth providers can be added without further changes.
    - Add ``OAuthConfig`` model in ``config/auth.py`` with provider,
      client_id, client_secret, redirect_uri, scope fields.
    - Add "Sign in with Google" button to the login page.

    ## Testing
    - Add unit tests for ``OAuthConfig`` in
      ``tests/test_auth_config.py`` (validation, defaults, env override).
    - Add integration test for the full Google OAuth flow in
      ``tests/integration/test_oauth_google.py``.
    - Manual: complete login with a real Google account in a dev
      environment; verify the user is created and the session cookie
      is set.

    ## Related issues
    Fixes #234

## Example body (bad)

    Added OAuth.
    ^^^^^^                                Too short, no structure
    see commit history
    ^^^^^^                                Unhelpful
    /close #234                           Should be in the Related issues section

## Format reminders

- Output as ``TITLE: <title>`` on the first line and ``BODY:`` followed
  by the body on subsequent lines.
- Keep the title on ONE line; the body may span multiple lines.
- Do not wrap the title in quotes, backticks, or code fences.
- Do not add a "Generated by ..." footer.
- Do not add a leading bullet ("-", "*", or numbered list) to the
  first line of the body.
"""
