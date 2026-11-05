# Contributing to MuFASA

Thank you for your interest in MuFASA! This guide explains how contributions work.

## Every contribution starts with an issue

Before writing code, please open an issue in the [issue tracker](https://github.com/mufasa-fusion/mufasa-fusion/issues/new/choose):

- **Bug report**: something does not work as documented.
- **New node**: a new input, processing or output node.
- **Feature request**: any other improvement, such as a new map type or a change to the Fusion Graph.

This lets us discuss the idea first, so nobody spends time on a change that does not fit the project.
Each issue type has a template that asks for everything we need to review your issue, so please fill in all required fields.

**Exception:** typos, broken links and small documentation fixes can go straight to a pull request.

## What happens next

New issues get the label `needs-triage`. A team member reviews the issue and then:

| Label | Meaning |
|---|---|
| `accepted` | The issue is confirmed and ready to be worked on. |
| `needs-info` | We need more details from you before we can decide. |
| *closed* | The issue is a duplicate, out of scope or will not be fixed. We add a short reason. |

## Working on an accepted issue

1. Comment on the issue that you are working on it.
2. Fork the repository (or create a branch, if you are a team member) and install the development dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

3. Make your change, add tests and make sure the test suite passes:

   ```bash
   pytest
   ```

4. Open a pull request against `dev` and reference the issue (e.g. `Closes #12`).

A team member reviews the pull request and merges it once everything is in order.

## What makes a good pull request

Before you ask for a review, please check:

**Scope**
- [ ] The pull request refers to an accepted issue (`Closes #12`).
- [ ] It does one thing. Unrelated changes go into a separate pull request.
- [ ] Your branch is up to date with the target branch.

**Code**
- [ ] The test suite passes (`pytest`). CI runs it on Python 3.10 to 3.14.
- [ ] New behaviour is covered by tests, and bug fixes come with a test that would have caught the bug.
- [ ] All classes and functions have docstrings.

**Documentation**
- [ ] User guide, examples or the node catalog are updated if behaviour changed.
- [ ] Breaking changes are clearly marked in the pull request description.


The pull request template contains a short version of this checklist that you tick off in the pull request.

By submitting a pull request, you agree that your contribution is licensed under the
project's [Apache 2.0 license](LICENSE).
