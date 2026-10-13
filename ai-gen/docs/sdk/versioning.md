# SDK Versioning

## Package version

The HEI Platform SDK follows semantic versioning.

- Major: breaking public service or model change.
- Minor: backward-compatible service, model, transport, or authentication capability.
- Patch: compatible fix, route remapping, diagnostic improvement, or documentation correction.

Milestone 5.11 begins at `0.1.0`. The API remains pre-1.0 while existing clients migrate and service contracts converge.

## Protocol version

`SdkConfiguration.apiVersion` is sent independently from the SDK package version. REST route changes within the same business contract do not require client changes; only the internal operation catalog changes.

## Compatibility handshake

`HEISdk.initialize()` calls Platform Health and evaluates:

- `minimumSdkVersion`, when supplied;
- `supportedSdkMajor`, when supplied.

An incompatible platform raises `VersionCompatibilityException` before business operations run.

## Artifact lineage

Request context can independently carry:

- Execution Package version;
- Repository Snapshot version;
- Context Capsule version;
- Knowledge version;
- Engineering Memory version.

These versions participate in diagnostics and cache freshness. They do not silently rewrite approved artifacts.

## Deprecation

Deprecated service methods remain available for at least one minor release and must identify their replacement in release notes. Internal REST mappings may change without deprecation because they are not public API.

## Migration guide

1. Add `@hei/platform-sdk` to the client.
2. Create one `HEISdk` instance at client startup.
3. Move authentication into an `IAuthenticationProvider`.
4. Replace URL builders and direct `fetch` calls with service methods.
5. Propagate existing correlation IDs using `RequestContext`.
6. Subscribe to SDK events for connection and retry UX.
7. Remove client-owned route constants only after behavior parity tests pass.

Existing clients can migrate one domain at a time. The SDK operation catalog preserves current backend compatibility while the public service contract remains stable.
