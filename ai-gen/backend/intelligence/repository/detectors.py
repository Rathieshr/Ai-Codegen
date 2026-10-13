from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .repository_snapshot import DiscoveredItem, RepositoryFile


TECH_RULES = [
    ("React", "Frontend", ["react", "tsx", "jsx"]),
    ("Angular", "Frontend", ["@angular/core", "angular.json"]),
    ("Vue", "Frontend", ["vue", "vue.config"]),
    ("MAUI", "Frontend", ["maui", "xaml", "net7.0-android", "net8.0-android"]),
    ("Flutter", "Frontend", ["flutter", "pubspec.yaml"]),
    ("ASP.NET", "Backend", ["microsoft.aspnetcore", "controllerbase", "[apicontroller]"]),
    ("Node", "Backend", ["express", "nestjs", "package.json"]),
    ("Spring", "Backend", ["spring-boot", "@restcontroller"]),
    ("FastAPI", "Backend", ["fastapi", "uvicorn"]),
    ("SQL Server", "Database", ["sqlserver", "mssql", "system.data.sqlclient"]),
    ("PostgreSQL", "Database", ["postgresql", "psycopg", "npgsql"]),
    ("SQLite", "Database", ["sqlite"]),
    ("Cosmos", "Database", ["cosmos"]),
    ("Azure", "Cloud", ["azure", "microsoft.identity", "azure-devops"]),
    ("AWS", "Cloud", ["amazonaws", "boto3", "aws"]),
    ("RabbitMQ", "Messaging", ["rabbitmq"]),
    ("Kafka", "Messaging", ["kafka"]),
    ("Azure AD", "Authentication", ["azure ad", "microsoft.identity", "entra"]),
    ("JWT", "Authentication", ["jwt", "jsonwebtoken", "bearer"]),
    ("OAuth", "Authentication", ["oauth"]),
    ("xUnit", "Testing", ["xunit"]),
    ("Jest", "Testing", ["jest"]),
    ("NUnit", "Testing", ["nunit"]),
]

ARCH_RULES = [
    ("MVVM", ["viewmodel", "observableobject", "xaml"]),
    ("MVC", ["controller", "model", "view"]),
    ("Clean Architecture", ["application", "domain", "infrastructure"]),
    ("Layered", ["controller", "service", "repository"]),
    ("Hexagonal", ["ports", "adapters"]),
    ("DDD", ["aggregate", "bounded context", "domain event"]),
    ("CQRS", ["commandhandler", "queryhandler", "mediatr"]),
]

PATTERN_RULES = [
    ("Repository Pattern", ["repository", "irepository"]),
    ("Dependency Injection", ["inject", "iservicecollection", "@injectable", "dependency injection"]),
    ("Mediator", ["mediatr", "mediator"]),
    ("Factory", ["factory"]),
    ("Observer", ["observer", "observable"]),
    ("Unit Of Work", ["unitofwork", "unit of work"]),
    ("Event Driven", ["event", "publish", "subscribe"]),
]

DOMAIN_MODULES = [
    "Authentication",
    "Telemetry",
    "Fault Monitoring",
    "Dashboard",
    "Reporting",
    "Notifications",
    "Asset Health",
    "Device Management",
    "Firmware",
    "Billing",
    "Work Orders",
]

DOMAIN_FLOWS = [
    "Login",
    "Telemetry Review",
    "Fault Event Review Flow",
    "Outage Investigation",
    "Device Health Review",
    "Firmware Rollout",
    "Alert Review",
    "Work Order Assignment",
]


class RepositoryDetectors:
    def detect_technologies(self, files: list[RepositoryFile]) -> list[DiscoveredItem]:
        corpus = _corpus(files)
        paths = " ".join(file.path.lower() for file in files)
        items = []
        for name, tech_type, signals in TECH_RULES:
            evidence = [signal for signal in signals if signal in corpus or signal in paths]
            if evidence:
                items.append(DiscoveredItem(name, tech_type, min(0.95, 0.55 + len(evidence) * 0.12), evidence))
        language_counts = Counter(file.language for file in files if file.language != "Unknown")
        for language, count in language_counts.items():
            items.append(DiscoveredItem(language, "Language", min(0.95, 0.45 + count / max(len(files), 1)), [f"{count} files"]))
        return _dedupe_items(items)

    def detect_architecture(self, files: list[RepositoryFile]) -> list[DiscoveredItem]:
        corpus = _corpus(files)
        paths = " ".join(file.path.lower() for file in files)
        items = []
        for name, signals in ARCH_RULES:
            evidence = [signal for signal in signals if signal in corpus or signal in paths]
            if evidence:
                items.append(DiscoveredItem(name, "Architecture", min(0.9, 0.45 + len(evidence) * 0.14), evidence))
        return _dedupe_items(items)

    def discover_applications(self, files: list[RepositoryFile], scan: dict[str, Any]) -> list[DiscoveredItem]:
        paths = [file.path.lower() for file in files]
        candidates: list[DiscoveredItem] = []
        if any("mobile" in path or path.endswith(".xaml") or path.endswith(".swift") or path.endswith(".kt") for path in paths):
            candidates.append(DiscoveredItem("Mobile App", "Application", 0.74, ["mobile folder or mobile UI files"]))
        if any("dashboard" in path or "portal" in path or path.endswith(".tsx") for path in paths):
            candidates.append(DiscoveredItem("Operations Dashboard", "Application", 0.72, ["dashboard/portal/frontend files"]))
        if any("controller" in path or "api" in path for path in paths):
            candidates.append(DiscoveredItem("Backend API", "Application", 0.78, ["controller/api files"]))
        if any("analytics" in path or "report" in path for path in paths):
            candidates.append(DiscoveredItem("Analytics Platform", "Application", 0.68, ["analytics/reporting files"]))
        if any("shared" in path or "common" in path for path in paths):
            candidates.append(DiscoveredItem("Shared Library", "Application", 0.64, ["shared/common folder"]))
        return _dedupe_items(candidates)

    def discover_modules(self, files: list[RepositoryFile]) -> list[DiscoveredItem]:
        corpus = _corpus(files)
        paths = " ".join(file.path.lower() for file in files)
        items = []
        rules = {
            "Authentication": ["auth", "login", "token", "jwt", "oauth"],
            "Telemetry": ["telemetry", "meter", "sensor"],
            "Fault Monitoring": ["fault", "outage", "alarm", "event"],
            "Dashboard": ["dashboard", "overview"],
            "Reporting": ["report", "analytics", "kpi"],
            "Notifications": ["notification", "alert"],
            "Asset Health": ["asset health", "device health", "health"],
            "Device Management": ["device", "meter", "asset"],
            "Firmware": ["firmware", "rollout", "upgrade"],
            "Billing": ["billing", "invoice", "payment"],
            "Work Orders": ["work order", "assignment", "dispatch"],
        }
        for name in DOMAIN_MODULES:
            signals = rules.get(name, [name.lower()])
            evidence = [signal for signal in signals if signal in corpus or signal in paths]
            if evidence:
                items.append(DiscoveredItem(name, "Module", min(0.92, 0.5 + len(evidence) * 0.1), evidence))
        for folder in _top_folders(files):
            if folder.lower() not in {"src", "docs", "test", "tests"}:
                items.append(DiscoveredItem(_title(folder), "Module", 0.45, [f"folder:{folder}"]))
        return _dedupe_items(items)

    def discover_flows(self, files: list[RepositoryFile]) -> list[DiscoveredItem]:
        corpus = _corpus(files)
        items = []
        rules = {
            "Login": ["login", "sign in", "authenticate"],
            "Telemetry Review": ["telemetry review", "review telemetry", "telemetry"],
            "Fault Event Review Flow": ["fault event", "critical fault", "fault"],
            "Outage Investigation": ["outage investigation", "investigate outage", "outage"],
            "Device Health Review": ["device health", "asset health"],
            "Firmware Rollout": ["firmware rollout", "firmware upgrade", "firmware"],
            "Alert Review": ["alert review", "alert", "notification"],
            "Work Order Assignment": ["work order", "assignment", "dispatch"],
        }
        for name in DOMAIN_FLOWS:
            evidence = [signal for signal in rules[name] if signal in corpus]
            if evidence:
                items.append(DiscoveredItem(name, "Flow", min(0.9, 0.48 + len(evidence) * 0.12), evidence))
        return _dedupe_items(items)

    def discover_dependencies(self, files: list[RepositoryFile]) -> list[DiscoveredItem]:
        items = []
        for file in files:
            if file.path.endswith(("package.json", ".csproj", "requirements.txt", "pyproject.toml", "pom.xml", "build.gradle")):
                names = re.findall(r'"([@\w.-]+)"\s*:', file.content)
                names += re.findall(r"<PackageReference\s+Include=\"([^\"]+)\"", file.content)
                names += re.findall(r"^([A-Za-z0-9_.-]+)==", file.content, flags=re.MULTILINE)
                for name in names[:40]:
                    items.append(DiscoveredItem(name, "Dependency", 0.75, [file.path]))
        return _dedupe_items(items)

    def discover_code_relationships(self, files: list[RepositoryFile]) -> dict[str, list[DiscoveredItem]]:
        services = []
        apis = []
        database_models = []
        for file in files:
            name = file.path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            lowered = file.path.lower()
            if "controller" in lowered:
                apis.append(DiscoveredItem(name, "Controller", 0.82, [file.path], metadata={"path": file.path}))
            if "service" in lowered:
                services.append(DiscoveredItem(name, "Service", 0.76, [file.path], metadata={"path": file.path}))
            if any(token in lowered for token in ["entity", "model", "repository", "dao"]):
                database_models.append(DiscoveredItem(name, "DatabaseEntity", 0.62, [file.path], metadata={"path": file.path}))
        return {
            "services": _dedupe_items(services),
            "apis": _dedupe_items(apis),
            "database_models": _dedupe_items(database_models),
        }

    def discover_patterns(self, files: list[RepositoryFile]) -> list[DiscoveredItem]:
        corpus = _corpus(files)
        paths = " ".join(file.path.lower() for file in files)
        items = []
        for name, signals in PATTERN_RULES:
            evidence = [signal for signal in signals if signal in corpus or signal in paths]
            if evidence:
                items.append(DiscoveredItem(name, "Pattern", min(0.9, 0.5 + len(evidence) * 0.12), evidence))
        return _dedupe_items(items)

    def discover_standards(self, files: list[RepositoryFile]) -> list[DiscoveredItem]:
        corpus = _corpus(files)
        rules = {
            "Structured logging": ["structured logging", "logger", "serilog"],
            "Input validation": ["validation", "validator", "required"],
            "Authorization checks": ["authorize", "authorization", "role-based"],
            "Central exception handling": ["exception handling", "error handler", "middleware"],
            "Unit tests required": ["unit test", "jest", "xunit", "nunit"],
            "Folder conventions documented": ["folder convention", "project structure"],
        }
        items = []
        for name, signals in rules.items():
            evidence = [signal for signal in signals if signal in corpus]
            if evidence:
                items.append(DiscoveredItem(name, "Standard", min(0.88, 0.48 + len(evidence) * 0.1), evidence))
        return _dedupe_items(items)


def _corpus(files: list[RepositoryFile]) -> str:
    parts: list[str] = []
    for file in files:
        parts.append(file.path.lower())
        parts.append(file.content.lower())
    return "\n".join(parts)


def _top_folders(files: list[RepositoryFile]) -> list[str]:
    folders = []
    for file in files:
        parts = file.path.split("/")
        if len(parts) > 1:
            folders.append(parts[0] if parts[0].lower() not in {"src", "app"} and len(parts) > 2 else parts[1])
    return [item for item, _ in Counter(folders).most_common(12)]


def _dedupe_items(items: list[DiscoveredItem]) -> list[DiscoveredItem]:
    by_name: dict[str, DiscoveredItem] = {}
    for item in items:
        key = item.name.lower()
        existing = by_name.get(key)
        if not existing or item.confidence > existing.confidence:
            by_name[key] = item
        elif existing:
            evidence = [*existing.evidence, *item.evidence]
            by_name[key] = DiscoveredItem(existing.name, existing.type, existing.confidence, list(dict.fromkeys(evidence)), existing.source, existing.metadata)
    return sorted(by_name.values(), key=lambda item: (-item.confidence, item.name))


def _title(value: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[-_\s]+", value) if part)
