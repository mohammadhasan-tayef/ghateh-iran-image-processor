# Storage Flow

Derived from [storage design](../architecture/storage-design.md).

```mermaid
flowchart LR
    Config[Server config\nconfig_key to mounted path]
    Admin[Admin sends config_key + alias]
    Root[StorageRoot\nexpected volume identity]
    Client[Client sends root_id + relative_path]
    Guard[Containment, Unicode/case, no-follow/reparse]
    Source[(Immutable source)]
    Obs[SourceObservation\nsize + mtime + streamed SHA-256]
    SourcePreview[(Regenerable source preview\norientation + resize only)]
    Working[working/{operation_id}]
    Candidate[(Immutable CandidateVersion\nUUID; internal RGB or RGBA)]
    Approval[Human approval in PostgreSQL]
    ExportJob[ExportJob\nimmutable naming snapshot]
    Partial[Target-volume .partial]
    Final[(2000x2000 8-bit sRGB RGB PNG\nno alpha; white)]

    Config --> Root
    Admin --> Root
    Client --> Root --> Guard --> Source
    Source -->|stat + bounded stream| Obs
    Obs -->|orientation + display resize| SourcePreview
    Obs -->|exact observation read| Working
    Working -->|checksum + atomic finalize| Candidate
    Candidate --> Approval --> ExportJob
    ExportJob --> Partial -->|verify + atomic rename| Final

    DB[(PostgreSQL descriptors, states, checksums)]
    Root --- DB
    Obs --- DB
    SourcePreview --- DB
    Candidate --- DB
    ExportJob --- DB
    Final --- DB
```
