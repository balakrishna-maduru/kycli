# Contributing to KyCLI

First off, thanks for taking the time to contribute! 🎉

The following is a set of guidelines for contributing to KyCLI. These are mostly guidelines, not rules. Use your best judgment, and feel free to propose changes to this document in a pull request.

## Code of Conduct

This project and everyone participating in it is governed by the [KyCLI Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to [balakrishnamaduru@gmail.com](mailto:balakrishnamaduru@gmail.com).

## How Can I Contribute?

### Reporting Bugs

This section guides you through submitting a bug report for KyCLI. Following these guidelines helps maintainers and the community understand your report, reproduce the behavior, and find related reports.

*   **Use the Bug Report Issue Template.** When you open a new issue, selected the "Bug Report" template to ensure all necessary details are included.
*   **Perform a search** to see if the problem has already been reported.
*   **Describe the bug clearly.** Include clear steps to reproduce the issue.

### Suggesting Enhancements

This section guides you through submitting an enhancement suggestion for KyCLI, including completely new features and minor improvements to existing functionality.

*   **Use the Feature Request Issue Template.**
*   **Describe the current behavior** and **explain the new behavior** you’d like to see.
*   **Why is this needed?** Explain how this enhancement would benefit the community.

### Pull Requests

1.  **Fork the repo** and create your branch from `master`.
2.  If you've added code that should be tested, add tests.
3.  If you've changed APIs, update the documentation.
4.  Ensure the test suite passes.
5.  Make sure your code follows the existing style conventions.
6.  Issue that pull request!

## Development Setup

1.  Clone the repository:
    ```bash
    git clone https://github.com/balakrishna-maduru/kycli.git
    cd kycli
    ```

2.  Create a virtual environment:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  Install dependencies:
    ```bash
    pip install .
    pip install -r requirements-dev.txt # If applicable, or install dev tools manually
    ```

4.  Run tests:
    ```bash
    pytest
    ```

## Styleguides

### Git Commit Messages

*   Use the present tense ("Add feature" not "Added feature")
*   Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
*   Limit the first line to 72 characters or less
*   Reference issues and pull requests liberally after the first line

### Python Style

*   We follow [PEP 8](https://www.python.org/dev/peps/pep-0008/).
*   Use `black` or `ruff` for formatting if available.

Thank you for contributing!
