<!-- =============================================================================
  menabò — an experiment in human-agent newsroom integration
 ------------------------------------------------------------------------------
  File:     spark-a/wordpress/NOTES.md
  Purpose:  WordPress service notes: mcp-adapter installation and the
            Contributor publication gate. The data/ dir here is runtime.
  Author:   Gianni Alessandroni
  Created:  2026-08-16
  License:  Apache-2.0 — see LICENSE
  Part of:  menabò https://github.com/GianniAlessandroni/menabo
============================================================================== -->

# WordPress service notes

- Image `wordpress:7.0.4-php8.4-apache`; content lives in `data/` (gitignored).
- Provisioning is scripted: `scripts/setup-wordpress.sh` installs core, the
  **WordPress/mcp-adapter** plugin pinned at `v0.6.1` (the old
  `Automattic/wordpress-mcp` is archived — never use it), the dedicated
  **`impaginatore` role** (a Contributor clone plus `upload_files`, so the
  newsroom delivers complete drafts with images — still no `publish_posts`),
  the `impaginatore` user on that role, and an Application Password for MCP.
- MCP endpoint (streamable HTTP, internal network only):
  `http://wordpress:80/wp-json/mcp/mcp-adapter-default-server`
  with `Authorization: Basic base64(impaginatore:<application password>)`.
- The container is **not** published on the host; the director browses through
  the staging nginx (`STAGING_URL`), which also defines `WP_HOME`/`WP_SITEURL`.
- The publication gate is the missing `publish_posts` capability. Do not grant
  a wider role or second credential "for testing" (SPEC §2.1) — the smoke test
  asserts that media upload succeeds AND that a publish attempt with the
  agent's credentials fails.
