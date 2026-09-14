# Changelog

All notable changes to MCP Lens will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Multi-layer evaluation engine (protocol, quality, security, LLM-assisted)
- Web UI for server management, tool inspection, and evaluation
- Support for Bearer token, API key, OAuth 2.0, and DCR authentication
- LLM-assisted evaluation with Anthropic, OpenAI, VertexAI, and Anthropic-Vertex adapters
- Combined JSON/PDF export with selectable sections
- False positive marking with justification persistence
- CLI tool (`mcp-lens`) for headless evaluation and CI integration
- Interactive `make setup` with menu-driven configuration
- SQLite persistence for server configs, auth tokens, and eval reports
- In-app About page with evaluation rules reference

## [0.1.0] - 2024-01-01

### Added
- Initial release
- MCP server connection and tool fetching
- Basic evaluation framework
