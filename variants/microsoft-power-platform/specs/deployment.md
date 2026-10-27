# Microsoft environment deployment sequence

1. Provision a licensed Power Platform environment with Copilot Studio, Power
   Apps and Power Automate capabilities. Verify connector, DLP and data residency
   policies with the tenant administrator. This was not available locally.
2. Build and review a **delegated Entra identity bridge**: validate issuer,
   audience, signature, expiry and user subject; map each subject to a ProcessMind
   user and active membership; enforce roles and organization on every request.
   Preserve CSRF/session protections for browser clients. This is a required
   backend change outside the isolated variant and has not been implemented.
3. Expose the API over a reviewed HTTPS endpoint reachable by the tenant.
   The ephemeral local Quick Tunnel is a demo mechanism, not an enterprise
   endpoint. Configure environment-specific host/client values and secrets in
   supported environment variables or secure connections, never in Power Fx.
4. Create a solution, custom connector for the verified OpenAPI operations,
   delegated OAuth connection and connection references. Test two users in
   different organizations, a revoked membership and viewer role before use.
5. Build the flows in [power-automate](power-automate.md), then the agent and
   canvas app. Microsoft documents [solution connector environment variables](https://learn.microsoft.com/en-us/connectors/custom-connectors/environment-variables)
   and [app connections](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/add-manage-connections).
6. Run tenant tests for real-time action response, asynchronous audit status,
   no-data fallback, evidence citations, duplicate request, timeout, DLP and
   sharing. Publish only after security and operational review.

No solution export, connector package, environment ID, credentials or cloud
deployment is included. The current ProcessMind session/CSRF authentication
cannot safely be represented as a shared custom connector credential. A per-user
bridge is a hard prerequisite, not a configuration toggle.
