from pydantic import BaseModel, ConfigDict, Field


class OAuthConfig(BaseModel):
    grant_type: str = "authorization_code"
    registration_endpoint: str | None = None
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    client_id: str | None = None
    client_secret_env: str | None = None
    scopes: list[str] = []


class ApiKeyConfig(BaseModel):
    location: str = "header"
    name: str = "X-API-Key"


class McpServerConfig(BaseModel):
    enabled: bool = True
    url: str
    transport: str = "streamable_http"
    ssl_verify: bool = True
    auth: bool = False
    description: str = ""
    auth_mode: str | None = None
    oauth: OAuthConfig | None = None
    api_key_config: ApiKeyConfig | None = None
    timeout: int = 30


class McpConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mcp_servers: dict[str, McpServerConfig] = Field(default_factory=dict, alias="mcpServers")


class ServerCreateRequest(BaseModel):
    name: str
    config: McpServerConfig


class ToolInfo(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict | None = None


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: dict | None = None
