# Zrb CLI v2 Migration Patterns

When upgrading APIs from v1 to v2, several breaking changes were introduced to improve functionality, security, and scalability.

## Key Changes and Mitigation Strategies

1. **Path Prefixing (`/v2/`):**
   - **Strategy:** Update HTTP routing or client base URLs to target `/v2/` resources. Ensure dual-routing is supported if deprecated v1 endpoints are kept alive temporarily.

2. **Standard Authentication Header:**
   - **Strategy:** Transition from custom headers like `X-Auth-Token` to standard RFC-compliant headers like `Authorization: Bearer <token>`. This enhances integration with standard reverse proxies and API gateways.

3. **Data Type Transition (Integer to UUID):**
   - **Strategy:** Update serialization schemas and database identifiers from integer types to standard string UUIDs. This prevents ID guessing attacks.

4. **Field Renaming (`done` to `completed`):**
   - **Strategy:** Implement robust mapping layers in DTOs/serializers to smoothly map between legacy states and updated states.

5. **Mandatory Project Partitioning (`project_id`):**
   - **Strategy:** Force contextual task creation by requiring `project_id`. Frontend clients must fetch active project contexts prior to task creation requests.

6. **Cursored Pagination:**
   - **Strategy:** Avoid offset/limit pagination in favor of cursored pagination (`items`, `total`, `next_cursor`) for performance scalability on large datasets.

## Backlinks
- [Journal HUD](../index.md)
