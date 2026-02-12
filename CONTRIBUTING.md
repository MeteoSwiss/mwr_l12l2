# Contributing

Thank you for your interest in contributing to **mwr_l12l2**! We welcome contributions from the community and are grateful for your support.

## Code of Conduct

This project adheres to the Contributor Covenant Code of Conduct. By participating, you are expected to uphold this code. Please read the full [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates. When you create a bug report, include as many details as possible:

- Use a clear and descriptive title
- Describe the exact steps to reproduce the problem
- Provide specific examples to demonstrate the steps
- Describe the behavior you observed and what you expected to see
- Include any error messages or stack traces
- Note your environment (Python version, OS, external dependencies like TROPoe, ECMWF tools, etc.)

### Suggesting Features

Feature suggestions are welcome! Please create an issue and include:

- A clear and descriptive title
- A detailed description of the proposed feature
- Explain why this feature would be useful for E-PROFILE or microwave radiometer retrievals
- Provide examples of how it would be used

### Contributing Code

1. Fork the repository
2. Create a new branch for your feature or bugfix
3. Make your changes following our coding standards
4. Write or update tests as needed
5. Ensure all tests pass and code quality checks succeed
6. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Poetry (for dependency management)
- Git
- External dependencies:
  - **podman** (for TROPoe container)
  - **TROPoe container**: `podman pull docker.io/davidturner53/tropoe`
  - **libeccodes0** and **libeccodes-tools** (for ECMWF data)
  - **mars** (optional, for ECMWF data requests)

### Setting Up Your Environment

1. Clone your fork of the repository:
   ```console
   $ git clone https://github.com/YOUR-USERNAME/mwr_l12l2.git
   $ cd mwr_l12l2
   ```

2. Install dependencies:
   ```console
   $ poetry install
   ```

3. Verify your setup by running the tests:
   ```console
   $ poetry run python -m unittest discover tests/
   ```

## Code Style and Quality

This project follows Python best practices and PEP 8 style guidelines.

### Formatting

- Use consistent indentation (4 spaces)
- Keep line length reasonable (typically < 120 characters)
- Follow PEP 8 naming conventions

### Testing Guidelines

- Write unit tests for all new code
- Place tests in the `tests/` directory
- Follow the existing test structure and naming conventions
- Use descriptive test names that explain what is being tested
- Ensure tests are reproducible and don't depend on external resources when possible

### Running Tests

Run all tests:
```console
$ poetry run python -m unittest discover tests/
```

Or with Poetry's test runner if configured:
```console
$ poetry run pytest
```

## Documentation

- Update documentation for any changed functionality
- Add docstrings to new functions, classes, and modules
- Follow the existing documentation style (compatible with Sphinx)
- Build documentation locally to verify changes:
  ```console
  $ cd docs
  $ make html
  ```

## Pull Request Process

1. **Update the CHANGELOG**: Add a brief description of your changes in **CHANGELOG.md**
2. **Update AUTHORS**: If this is your first contribution, add your name to the **AUTHORS** file
3. **Create a Pull Request**: Ensure you:
   - Provide a clear description of the changes
   - Reference any related issues (e.g., "Closes #123")
   - Ensure all CI checks pass
4. **Code Review**: A maintainer will review your PR. Be prepared to make changes based on feedback
5. **Merge**: Once approved and all checks pass, a maintainer will merge your PR

### Commit Messages

Write clear, concise commit messages:

- Use the imperative mood ("Add feature" not "Added feature")
- Start with a capital letter
- Keep the first line under 50 characters
- Add a blank line followed by a detailed description if needed

Example:
```text
Add validation for input parameters

- Validate that input is not None
- Raise ValueError for invalid types
- Add unit tests for validation logic
```

## Specific Contribution Areas

### Instrument Configuration Files

If you're contributing a new instrument configuration:

- Follow the existing configuration file structure
- Include all required fields
- Test with actual or simulated data from the instrument
- Document any instrument-specific quirks or requirements

### Retrieval Algorithms

For contributions to retrieval algorithms:

- Ensure compatibility with TROPoe
- Test with various atmospheric conditions
- Document the scientific basis and any assumptions
- Include references to relevant publications

### ECMWF Integration

When modifying ECMWF data handling:

- Ensure compatibility with both MARS and CDS APIs
- Test with different forecast times and domains
- Handle error cases gracefully
- Document any new ECMWF parameters used

## License

By contributing to this project, you agree that your contributions will be licensed under the BSD-3-Clause License.

## Questions?

If you have questions about contributing, please:

- Check existing issues and discussions
- Review the [documentation](https://mwr-l12l2.readthedocs.io)
- Create a new issue with your question
- Contact the maintainers

Thank you for contributing to mwr_l12l2!
