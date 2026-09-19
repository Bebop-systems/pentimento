# Security

## Threat model

Pentimento is a local, single-user tool. It binds `127.0.0.1` on a random
port, rejects requests carrying a `Host` header it did not issue (which stops
DNS rebinding reaching it through a browser tab you already have open), and
makes no network calls after first-run setup.

It is meant to defend a photograph's metadata against **casual inspection**:
someone opening the properties panel, an automated scraper, a social platform
reading Exif on upload.

It is **not** meant to defeat forensic analysis, and by design it cannot. The
payload gate guarantees the image bitstream survives byte-for-byte, which
means sensor noise, quantization tables and encoder fingerprints survive too.
Preserving the image exactly and altering provenance claims are opposing
goals, and this tool chooses preservation. Do not rely on it where provenance
matters.

## Reporting a vulnerability

Open a [security advisory](https://github.com/Bebop-systems/pentimento/security/advisories/new)
rather than a public issue. A reply should come within a week.

Things worth reporting:

- A path that escapes the output directory
- A way to make the app read or write outside its session directory
- A gate that passes on a file it should have rejected
- Any network request the app makes that is not the one-time ExifTool fetch
- A way for a crafted image to cause code execution

Things that are known and documented rather than bugs: unsigned binaries,
the forensic limits above, and metadata that ExifTool itself cannot remove
(noted in the interface where it occurs).

## Supply chain

ExifTool is pinned to a specific version and fetched from SourceForge, which
is where its author publishes. The archive is checked to be an archive before
extraction, and tar extraction uses Python's `filter="data"` mode, which
refuses absolute paths and traversal.
