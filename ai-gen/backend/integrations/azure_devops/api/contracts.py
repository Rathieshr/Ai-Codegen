from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RegisterConnectionRequest(BaseModel):
    # Extras reach the application service so credential-shaped fields can be
    # rejected without FastAPI echoing their values in a validation response.
    model_config = ConfigDict(extra="allow")

    organization_url: str = Field(alias="organizationUrl")
    organization_name: str = Field(default="", alias="organizationName")
    project_id: str = Field(default="", alias="projectId")
    project_name: str = Field(default="", alias="projectName")
    authentication_mode: str = Field(default="PAT", alias="authenticationMode")
    secret_reference: str = Field(alias="secretReference")
    permissions: list[str] = Field(default_factory=list)

    def as_service_input(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


class WIQLRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project: str
    query: str


class WebhookRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    event_type: str = Field(default="", alias="eventType")
    connection_id: str = Field(default="", alias="connectionId")
    project_id: str = Field(default="", alias="projectId")
    resource: dict[str, Any] = Field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


class AzureDevOpsSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_id: str = Field(alias="connectionId")
    sync_type: str = Field(default="ManualSync", alias="syncType")


class AzureDevOpsReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_id: str = Field(alias="connectionId")
