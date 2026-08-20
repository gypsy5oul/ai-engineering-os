---
name: api-design
description: Design and review interface contracts - REST, GraphQL, gRPC, events or file-based protocols - including versioning, compatibility, errors and pagination. Use when adding or changing any interface consumed outside its own module. Breaking changes require human approval.
---

# API design

The contract is the product for everyone who is not inside your module. Design it before the implementation, and version it as if you cannot reach the consumers, because usually you cannot.

## Design order

1. **Consumers and their use cases.** An API designed without a named consumer is guesswork.
2. **Resources or messages**, named from the domain, not from the database.
3. **Operations**, each with its full outcome set: success, each failure, and the partial cases.
4. **Data shapes**, with required and optional fields, types, units, timezone handling and size bounds.
5. **Errors**: a stable machine-readable code, a human-readable message, and whether retrying could help.
6. **Idempotency** for anything that can be retried or redelivered. Say how the caller expresses it.
7. **Pagination, filtering and sorting**, with a stated maximum page size. Unbounded list endpoints are a performance finding.
8. **Versioning and compatibility.**
9. **Authentication and authorization** per operation, including which fields differ by caller identity.
10. **Rate limits and quotas**, and what the caller sees when they are hit.

## Compatibility rules

Additive is safe: new optional fields, new endpoints, new enum values **only if consumers were told to tolerate unknown values**.

Breaking includes: removing or renaming a field, tightening validation, changing a type or unit, changing an error code, changing default behaviour, making an optional field required, changing pagination semantics.

A breaking change is AP-06. Escalate before designing around it. The standard path is expand → migrate → contract: add the new form, move consumers, remove the old form in a later release.

## Style-specific notes

- **REST**: nouns for resources, HTTP verbs for operations, meaningful status codes, and no verbs in paths for standard CRUD. Use a consistent error body across the whole surface.
- **GraphQL**: the schema is the contract; deprecate rather than remove; bound query depth and complexity or accept a denial-of-service surface.
- **gRPC**: never reuse a field number; reserve removed ones; treat proto compatibility rules as binding.
- **Events**: the event is a fact about the past, named in the past tense. Include an event id, a timestamp, a schema version and enough context that a consumer need not call back. Assume at-least-once delivery and design consumers to be idempotent.
- **File and batch protocols** (for example SFTP drops): the filename convention, the encoding, the completeness marker, the ordering guarantee and the duplicate-handling rule are all part of the contract. Write them down.

## Documentation

The contract is machine-readable where the ecosystem supports it (OpenAPI, proto, GraphQL SDL, JSON Schema). Human prose supplements it; it does not replace it.

## Review checklist

- Every operation's failure modes documented, not just the happy path.
- Every list operation bounded.
- Every mutating operation's idempotency stated.
- Every field's units and timezone stated.
- Backward compatibility assessed explicitly, with breaking changes escalated.
- Authorization stated per operation, not assumed from the endpoint's location.
