# Redis Streams Architecture

Redis Streams is an append-only log data structure. Key mechanics include:

- **Stream Capping**: Keeps memory bounded using `MAXLEN` or `MINID` on `XADD` (e.g., `XADD mystream MAXLEN ~ 100000 * field value`).
- **Consumer Groups**: Coordinated read operations via `XREADGROUP`.
- **Pending Entries List (PEL)**: Tracks unacknowledged reads. Read messages remain in the PEL until explicitly acknowledged with `XACK`.
- **Claiming Orphans**: Dead or timed-out consumers can be handled by periodically querying `XPENDING` and claiming outstanding messages with `XCLAIM`.

## Backlinks
- [Technical Index](index.md)
- [Notifier Subsystem Project](../projects/notifier.md)
