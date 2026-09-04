from pydantic import BaseModel


class OAuthConfig(BaseModel):
    grant_type: str = "authorization_code"
    registration_endpoint: str | None = None
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    client_id: str | None = None
    client_secret_env: str | None = None
    scopes: list[str] = []


class McpServerConfig(BaseModel):
    enabled: bool = True
    url: str
    transport: str = "streamable_http"
    ssl_verify: bool = True
    auth: bool = False
    description: str = ""
    auth_mode: str | None = None
    oauth: OAuthConfig | None = None
    timeout: int = 30


class McpConfig(BaseModel):
    mcpServers: dict[str, McpServerConfig] = {}


class ServerCreateRequest(BaseModel):
    name: str
    config: McpServerConfig


class ToolInfo(BaseModel):
    name: str
    description: str | None = None
    inputSchema: dict | None = None


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: dict | None = None
