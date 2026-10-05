# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately, through GitHub's
[private vulnerability reporting](https://github.com/ianderso/us-places-mcp/security/advisories/new)
(the **Report a vulnerability** button on the repository's Security tab), not
in a public issue. Include what an attacker controls, what they gain, and the
steps to reproduce it.

You should hear back within a week. Fixes are released for the latest version
only.

## Scope

In scope: this server — the requests it makes, the files it writes (its
cache), and anything a tool argument or an API response can make it do.

Out of scope: OpenHistoricalMap and BLM's PLSS service, which this project
does not operate.

## The security model, briefly

- **No credentials.** Both services are public; the server holds no key.
- **Two hosts.** A request hook refuses any request whose host is not one of
  the two configured services. Both URLs must be https.
- **Inputs are validated** before they reach a query: coordinates must be
  finite and in range; states come from a fixed table; township, range,
  section and lot numbers are digits; meridians come from a fixed table; a
  county name is escaped character by character into the Overpass query. No
  free text reaches an ArcGIS `where` clause.
- **The only local writes are the cache,** under `US_PLACES_CACHE_DIR`, in
  files named by a hash of the request, written atomically.
- **Responses carry third-party text.** Atlas event and statute text reaches
  the model verbatim. The server's instructions tell the model to treat it as
  data, never as instructions.
- **`US_PLACES_CONTACT` is checked** for newlines and parentheses before it is
  placed in the User-Agent header.
