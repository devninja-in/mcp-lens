#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
ENV_EXAMPLE="$ROOT_DIR/.env.example"

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
RESET='\033[0m'

info()  { echo -e "${CYAN}➜${RESET} $*"; }
ok()    { echo -e "${GREEN}✓${RESET} $*"; }
warn()  { echo -e "${YELLOW}!${RESET} $*"; }
header(){ echo -e "\n${BOLD}$*${RESET}"; }

# --- helpers ---

prompt_value() {
    local label="$1" default="$2" var_name="$3"
    local value
    read -rp "  $label [$default]: " value
    value="${value:-$default}"
    eval "$var_name=\"\$value\""
}

prompt_secret() {
    local label="$1" var_name="$2"
    local value
    read -rsp "  $label: " value
    echo
    eval "$var_name=\"\$value\""
}

set_env_var() {
    local key="$1" value="$2"
    if grep -qE "^${key}=" "$ENV_FILE" 2>/dev/null; then
        sed -i.bak "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
        rm -f "$ENV_FILE.bak"
    elif grep -qE "^#\s*${key}=" "$ENV_FILE" 2>/dev/null; then
        sed -i.bak "s|^#\s*${key}=.*|${key}=${value}|" "$ENV_FILE"
        rm -f "$ENV_FILE.bak"
    else
        echo "${key}=${value}" >> "$ENV_FILE"
    fi
}

# --- install deps ---

install_deps() {
    header "Installing dependencies"

    if command -v uv &>/dev/null; then
        info "Installing Python dependencies (uv sync)..."
        (cd "$ROOT_DIR" && uv sync --extra dev)
    else
        warn "uv not found — install from https://docs.astral.sh/uv/"
        info "Falling back to pip..."
        (cd "$ROOT_DIR" && pip install -e ".[dev]")
    fi
    ok "Python dependencies installed"

    info "Installing frontend dependencies..."
    (cd "$ROOT_DIR/src/frontend" && npm install --silent)
    ok "Frontend dependencies installed"
}

install_llm_extra() {
    local provider="$1"
    local extra=""
    case "$provider" in
        openai)          extra="eval-openai" ;;
        anthropic)       extra="eval-anthropic" ;;
        vertexai)        extra="eval-vertexai" ;;
        anthropic-vertex) extra="eval-anthropic-vertex" ;;
        *) return ;;
    esac

    info "Installing $extra dependencies..."
    if command -v uv &>/dev/null; then
        (cd "$ROOT_DIR" && uv sync --extra dev --extra "$extra")
    else
        (cd "$ROOT_DIR" && pip install -e ".[$extra]")
    fi
    ok "$extra dependencies installed"
}

# --- .env handling ---

ensure_env_file() {
    if [ -f "$ENV_FILE" ]; then
        local choice
        echo ""
        warn ".env file already exists."
        read -rp "  Overwrite / Merge / Keep? [O/m/k, default=m]: " choice
        choice="${choice:-m}"
        case "$choice" in
            [Oo]*)
                cp "$ENV_EXAMPLE" "$ENV_FILE"
                ok ".env overwritten from .env.example"
                return 0  # overwrite
                ;;
            [Kk]*)
                ok ".env kept as-is"
                return 1  # keep — skip config
                ;;
            *)
                ok ".env will be merged (existing values preserved, new ones added)"
                return 0  # merge
                ;;
        esac
    else
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        ok ".env created from .env.example"
        return 0
    fi
}

# --- LLM configuration ---

configure_llm() {
    header "LLM Evaluation Setup"
    echo "  Choose an LLM provider for evaluation checks."
    echo "  This is optional — skip to use static analysis only."
    echo ""
    echo "  1) openai"
    echo "  2) anthropic"
    echo "  3) vertexai (Gemini)"
    echo "  4) anthropic-vertex (Claude on VertexAI)"
    echo "  5) Skip (no LLM evaluation)"
    echo ""

    local provider_choice
    read -rp "  Provider [1-5, default=5]: " provider_choice
    provider_choice="${provider_choice:-5}"

    case "$provider_choice" in
        1)
            set_env_var "EVAL_LLM_PROVIDER" "openai"
            ok "Provider: openai"

            local model
            prompt_value "Model" "gpt-4o" model
            set_env_var "EVAL_LLM_MODEL" "$model"

            local api_key
            prompt_secret "API key (input hidden)" api_key
            if [ -n "$api_key" ]; then
                set_env_var "EVAL_LLM_API_KEY" "$api_key"
                ok "API key saved"
            fi

            local base_url
            prompt_value "Base URL (for Azure/Ollama/vLLM, or leave empty)" "" base_url
            if [ -n "$base_url" ]; then
                set_env_var "EVAL_LLM_BASE_URL" "$base_url"
            fi

            install_llm_extra "openai"
            ;;
        2)
            set_env_var "EVAL_LLM_PROVIDER" "anthropic"
            ok "Provider: anthropic"

            local model
            prompt_value "Model" "claude-sonnet-4-20250514" model
            set_env_var "EVAL_LLM_MODEL" "$model"

            local api_key
            prompt_secret "API key (input hidden)" api_key
            if [ -n "$api_key" ]; then
                set_env_var "EVAL_LLM_API_KEY" "$api_key"
                ok "API key saved"
            fi

            install_llm_extra "anthropic"
            ;;
        3)
            set_env_var "EVAL_LLM_PROVIDER" "vertexai"
            ok "Provider: vertexai (Gemini)"

            local model
            prompt_value "Model" "gemini-2.5-flash" model
            set_env_var "EVAL_LLM_MODEL" "$model"

            local project
            prompt_value "GCP project ID" "" project
            if [ -n "$project" ]; then
                set_env_var "EVAL_LLM_PROJECT" "$project"
            fi

            local location
            prompt_value "GCP region" "us-central1" location
            set_env_var "EVAL_LLM_LOCATION" "$location"

            local api_key
            echo "  API key (leave empty to use Application Default Credentials):"
            prompt_secret "  API key (input hidden, press Enter to skip)" api_key
            if [ -n "$api_key" ]; then
                set_env_var "EVAL_LLM_API_KEY" "$api_key"
                ok "API key saved"
            else
                ok "Using Application Default Credentials"
            fi

            install_llm_extra "vertexai"
            ;;
        4)
            set_env_var "EVAL_LLM_PROVIDER" "anthropic-vertex"
            ok "Provider: anthropic-vertex (Claude on VertexAI)"

            local model
            prompt_value "Model" "claude-sonnet-4-20250514" model
            set_env_var "EVAL_LLM_MODEL" "$model"

            local project
            prompt_value "GCP project ID" "" project
            if [ -n "$project" ]; then
                set_env_var "EVAL_LLM_PROJECT" "$project"
            fi

            local location
            prompt_value "GCP region" "us-east5" location
            set_env_var "EVAL_LLM_LOCATION" "$location"

            local creds
            prompt_value "Service account JSON path (or leave empty for ADC)" "" creds
            if [ -n "$creds" ]; then
                set_env_var "GOOGLE_APPLICATION_CREDENTIALS" "$creds"
            fi

            install_llm_extra "anthropic-vertex"
            ;;
        *)
            ok "Skipping LLM configuration (static analysis only)"
            ;;
    esac
}

# --- full configuration ---

configure_all() {
    header "General Settings"

    local port
    prompt_value "Backend port" "5002" port
    set_env_var "BACKEND_PORT" "$port"

    prompt_value "Frontend port" "5173" port
    set_env_var "FRONTEND_PORT" "$port"

    echo ""
    echo "  Database:"
    echo "  1) SQLite (default, no setup needed)"
    echo "  2) PostgreSQL"
    local db_choice
    read -rp "  Choose [1-2, default=1]: " db_choice
    db_choice="${db_choice:-1}"

    if [ "$db_choice" = "2" ]; then
        local db_url
        prompt_value "PostgreSQL URL" "postgresql://user:password@localhost:5432/mcp_lens" db_url
        set_env_var "DATABASE_URL" "$db_url"
    else
        ok "Using SQLite (./mcp_secrets.db)"
    fi

    local persist
    read -rp "  Persist OAuth tokens across sessions? [y/N, default=N]: " persist
    persist="${persist:-n}"
    case "$persist" in
        [Yy]*)
            set_env_var "PERSIST_OAUTH_TOKENS" "true"
            ;;
        *)
            set_env_var "PERSIST_OAUTH_TOKENS" "false"
            ;;
    esac

    configure_llm
}

# --- main ---

main() {
    echo ""
    echo -e "${BOLD}MCP Lens Setup${RESET}"
    echo "=============="
    echo ""
    echo "  1) Quick setup (use defaults for everything)"
    echo "  2) Configure LLM evaluation"
    echo "  3) Configure all settings"
    echo ""

    local mode
    read -rp "Choose [1-3, default=1]: " mode
    mode="${mode:-1}"

    install_deps

    case "$mode" in
        2)
            if ensure_env_file; then
                configure_llm
            fi
            ;;
        3)
            if ensure_env_file; then
                configure_all
            fi
            ;;
        *)
            if [ ! -f "$ENV_FILE" ]; then
                cp "$ENV_EXAMPLE" "$ENV_FILE"
                ok ".env created from .env.example"
            else
                ok ".env already exists, keeping as-is"
            fi
            ;;
    esac

    # Generate encryption key if not already set
    if [ -f "$ENV_FILE" ] && ! grep -qE "^MCP_LENS_ENCRYPTION_KEY=" "$ENV_FILE"; then
        local key
        key=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
        set_env_var "MCP_LENS_ENCRYPTION_KEY" "$key"
        ok "Generated encryption key for database secrets"
    fi

    echo ""
    ok "Setup complete. Run ${BOLD}make start${RESET} to launch MCP Lens."
    echo ""
}

main "$@"
