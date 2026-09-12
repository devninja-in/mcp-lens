# Contributing to MCP Lens

Thank you for your interest in contributing to MCP Lens! This guide will help you get started.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone <your-fork-url>`
3. Run `make setup` to install dependencies and configure your environment
4. Create a branch: `git checkout -b feature/your-feature-name`

## Development Setup

```bash
make setup          # Interactive setup (installs deps, configures .env)
make start          # Start backend + frontend
make test           # Run Python tests
make lint           # TypeScript type check
```

See the [README](README.md) for full setup details.

## Making Changes

### Code Style

- **Python**: Follow PEP 8. Use type hints for function signatures. Run `ruff check` before committing.
- **TypeScript/React**: Follow existing component patterns. Run `npx tsc --noEmit` to verify types.
- **No unnecessary comments**: Code should be self-documenting. Only add comments when the *why* is non-obvious.

### Testing

- All new backend features must include tests in `tests/`.
- Run `make test` to verify all 377+ tests pass before submitting.
- Tests must not call external services or mutate production systems.
- Use mocks for external API calls (LLM providers, MCP servers).

### Security

- Never log secrets, API keys, bearer tokens, or credentials.
- Use the `redact_secrets()` function from `src/app/eval/redaction.py` for any user-facing output that might contain sensitive data.
- Never commit `.env` files, service account keys, or database files.
- The LLM evaluation must never execute actual MCP tool calls — only simulate tool selection.

### Commits

- Write clear, concise commit messages describing *what* and *why*.
- Keep commits focused — one logical change per commit.
- Ensure tests pass before committing.

## Pull Requests

1. Update your branch with the latest `main`: `git rebase main`
2. Ensure all tests pass: `make test`
3. Ensure TypeScript compiles: `make lint`
4. Open a pull request with:
   - A clear title describing the change
   - A description explaining what changed and why
   - Any relevant issue numbers

### PR Review Checklist

- [ ] Tests pass (`make test`)
- [ ] TypeScript compiles (`make lint`)
- [ ] No secrets or credentials in the diff
- [ ] New features include tests
- [ ] Breaking changes are documented

## Reporting Issues

- Use GitHub Issues to report bugs or request features.
- Include steps to reproduce for bugs.
- Include your Python version, Node version, and OS.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code.

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
