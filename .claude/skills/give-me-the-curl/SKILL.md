---
name: give-me-the-curl
description: Use when the user says "give me the curl", "give me a curl for X", "curl the payload endpoint", or otherwise wants a ready-to-run curl command for one of this project's endpoints. Builds the command with a real, live auth token fetched from the appropriate core.services provisioner (not a placeholder) and copies it straight to the clipboard.
---

# Give me the curl

Produces a **ready-to-paste-and-run** curl command — not a template with
`<TOKEN>` placeholders. That means an actual token has to be fetched from
the running app before the command can be built.

## Procedure

1. **Make sure the app is reachable.** Prefer the Docker Compose stack
   (matches what's documented in the README as the default way to run this
   project): `docker-compose up -d --build`, then
   `docker-compose exec web python manage.py migrate` if needed. The app is
   then at `http://localhost:8000`.

2. **Fetch a real token from the relevant `core.services` provisioner** —
   don't invent one or reuse a stale value from memory. For the
   device-payload endpoint, that's `TokenProvisioner.get_ingest_client_auth_key()`:

   ```
   docker-compose exec web python manage.py shell -c "
   from core.services import TokenProvisioner
   print(TokenProvisioner.get_ingest_client_auth_key())
   "
   ```

   (If running without Docker, swap in `uv run python manage.py shell -c "..."`
   with the right env vars — see the README's "Without Docker" section.)

   If a future endpoint needs a different kind of client/token, use
   whatever `core.services` (or the relevant app's `services.py`) provides
   for it — the point is always a *live* value from the actual provisioning
   service, not a hardcoded example key.

3. **Pick the endpoint.** If the user names one (or a scenario that implies
   one), use that. **If they don't specify anything — just "give me the
   curl" — default to `POST /api/payloads/`**, the device-payload ingestion
   endpoint. It's the only endpoint this project has today; if more exist
   by the time you're reading this and it's no longer obviously "the"
   endpoint, ask which one instead of guessing.

4. **Build the curl command** with:
   - The method + URL from step 3 (check the app's `urls.py` for the exact
     path).
   - `-H "Content-Type: application/json"`.
   - `-H "Authorization: Token <the real key from step 2>"`.
   - A request body matching what that endpoint actually expects. For the
     default (`POST /api/payloads/`) with no other scenario specified, the
     body is the **exact example from the original spec** — reproduce it
     verbatim, don't paraphrase or simplify it:

     ```json
     {
       "fCnt": 100,
       "devEUI": "abcdabcdabcdabcd",
       "data": "AQ==",
       "rxInfo": [
         {"gatewayID": "1234123412341234", "name": "G1", "time": "2022-07-19T11:00:00", "rssi": -57, "loRaSNR": 10}
       ],
       "txInfo": {"frequency": 86810000, "dr": 5}
     }
     ```

     If the user asks for a curl for a *different* scenario (a failing
     payload, a different devEUI, a different endpoint entirely), build the
     body/URL for that instead — the spec example above is only the
     default when they give no other specifics.

5. **Copy it to the clipboard**, don't just print it — that's the point of
   the request:

   ```
   cat > /tmp/curl_command.txt << 'EOF'
   curl -X POST http://localhost:8000/api/payloads/ \
     -H "Content-Type: application/json" \
     -H "Authorization: Token <real-token-here>" \
     -d '{ ... }'
   EOF
   pbcopy < /tmp/curl_command.txt
   ```

   Also show the command in the response so the user can see what's about
   to be on their clipboard, and clean up the temp file afterward.

6. **Flag known-conflict cases before the user is surprised by them.**
   `(device, fCnt)` is unique — if the exact spec example (`fCnt: 100`,
   `devEUI: "abcdabcdabcdabcd"`) has already been POSTed against whatever
   database this is hitting, running it again will correctly return a
   `409 Conflict` (`{"error": "duplicate_payload", ...}"`), not a `201`.
   That's expected duplicate-detection behavior, not a bug — say so up
   front rather than letting it look like something broke.
