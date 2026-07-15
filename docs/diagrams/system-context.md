# System Context

Derived from [system architecture](../architecture/system-architecture.md).

```mermaid
flowchart LR
    Operator[Operator / Reviewer]
    Admin[Administrator]
    System[Ghateh Iran Image Processor]
    Drive[(Approved external drive)]
    Models[(Verified local model files)]

    Operator -->|LAN browser: batches, review, export| System
    Admin -->|Users, roots, models, policy| System
    System -->|Read immutable originals; write versioned outputs| Drive
    System -->|Load by verified checksum| Models

    note[No paid API or cloud image-processing dependency]
    note -. constraint .-> System
```
