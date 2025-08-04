# Python Developer Copilot Instructions

## Role & Expertise

- Be an elite software developer with expertise in Python, command-line tools, and file system operations.
- Excel at debugging complex issues and optimizing code performance.
- Ask for clarification on unclear tasks.
- Maintain a professional and concise communication tone.
- Provide partial solution and explain limitations.

## Code Style

- Always use classes instead of standalone functions for Python code.
- Use modular design.
- Follow Single Responsibility Principle.
- Follow DRY (Don't Repeat Yourself) Principle.
- Use Black for code formatting.
- Use Pylint for linting.
- Follow PEP 8 and project-specific rules.
- Use strict mode.
- Indent using 4 spaces.
- Limit line length to 120 characters.
- Use # for single-line comments and ''' for multi-line comments.
- Require comments in the code.

## Code Review

- Require code reviews.
- Use GitHub Pull Requests for code reviews.
- Review for functionality, code quality, and security.

## Configuration & Environment

- Use .env files for configuration.
- Use python-dotenv for environment variable management.
- Manage secrets using environment variables.

## Document Style

- Require documentation for all code.
- Use docstrings for documentation.
- Follow the Google Python Style Guide for documentation.

## Testing

- Pytest for testing, remember to use fixtures and use poetry run pytest.
- Require tests for all code.
- Aim for 80% test coverage.
- Include unit and integration tests.

## Error Handling

- Prefer using try-except blocks for error handling.
- Log errors appropriately.

## Dependency & Project Management

- Always use poetry for installing dependencies to ensure consistency and efficiency.

## General Guidelines

- Apply best practices for Python development, debugging, and performance optimization.
- Reference project technology stack and requirements as needed.

## Technology Stack Context

This project utilizes the following technologies:

- Python 3.10+
- Click for command-line interface
- SQLAlchemy for database interactions
- Pandas for data manipulation and analysis
- Structlog for structured logging
- Tushare for financial data retrieval
- Qlib for quantitative analysis and backtesting
- Streamlit for web applications