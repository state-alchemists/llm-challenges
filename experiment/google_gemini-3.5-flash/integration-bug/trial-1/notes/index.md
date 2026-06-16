# Zaruba Session Journal

## Active Constraints & Preferences
- Avoid changing public interfaces of existing classes (e.g., `Inventory`, `PaymentGateway`).
- Ensure no negative stock, no charge mismatches, and no double charges.
- Use `asyncio.Lock` for concurrency-safe state transitions in asynchronous environments.

## Recent Insights
- **[Checkout Transaction Isolation](technical/checkout-transaction-isolation.md)**: Solved concurrent race conditions via reserve-then-charge-or-rollback pattern.

## Projects
- **[Checkout Service](projects/checkout-service.md)**

## Backlinks
(none)
