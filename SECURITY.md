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

Out of scope: OpenHistoricalMap, BLM's PLSS service, USGS's services and
bucket, and Harvard Dataverse, which this project does not operate.

## The security model, briefly

- **No credentials.** Every service is public; the server holds no key.
- **A fixed set of hosts.** A request hook refuses any request whose host is
  not one of the configured services or Dataverse's file store. Every URL must
  be https. A download follows at most three redirects, each only to one of
  those hosts.
- **Inputs are validated** before they reach a query: coordinates must be
  finite and in range; states come from a fixed table; township, range,
  section and lot numbers are digits; meridians and GNIS classes come from
  fixed tables; a county name is escaped character by character into the
  Overpass query. No free text reaches an ArcGIS `where` clause or
  `layerDefs`: a place name goes to GNIS only as `find`'s search text, and a
  county is matched after the answer arrives. Local SQLite searches use bound
  parameters.
- **The only local writes are the cache,** under `US_PLACES_CACHE_DIR`, in
  files named by a hash of the request, written atomically, and the two
  datasets in its `data` folder. A download is capped at 64 MB, checked
  against its publisher's checksum (Dataverse's MD5, or the S3 ETag of USGS's
  bucket) before it is loaded, and deleted if it fails; the post-office
  database is built aside and moved into place whole.
- **Responses carry third-party text.** Atlas event and statute text, place
  names and post-office names reach the model verbatim. The server's instructions tell the model to treat it as
  data, never as instructions.
- **`US_PLACES_CONTACT` is checked** for newlines and parentheses before it is
  placed in the User-Agent header.
