# Storage Flow

Derived from [storage design](../architecture/storage-design.md).

```mermaid
flowchart LR
    Client[Client sends root_id + relative_path]
    Resolver[Storage root resolver]
    Guard[Normalize, contain, no-follow / reparse checks]
    Original[(inbox/ immutable original)]
    Working[working/{operation_id}/]
    Partial[Target-volume .partial]
    Candidate[(candidates/{asset}/{version}.png)]
    Review[Human approval in PostgreSQL]
    ExportPartial[exports/... .partial]
    Final[(exports/{batch}/final.png)]

    Client --> Resolver --> Guard --> Original
    Original -->|stream read; no overwrite| Working
    Working -->|copy/write + flush + checksum| Partial
    Partial -->|atomic same-volume no-replace rename| Candidate
    Candidate --> Review
    Review -->|approved candidate only| ExportPartial
    ExportPartial -->|verify + atomic rename| Final

    DB[(PostgreSQL descriptors, checksums, operation state)]
    Resolver --- DB
    Candidate --- DB
    Review --- DB
    Final --- DB
```
