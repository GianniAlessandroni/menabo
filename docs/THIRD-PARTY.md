<!-- =============================================================================
  menabò — an experiment in human-agent newsroom integration
 ------------------------------------------------------------------------------
  File:     docs/THIRD-PARTY.md
  Purpose:  Licenses of third-party components run as unmodified services
            in containers or used as pinned dependencies.
  Author:   Gianni Alessandroni
  Created:  2026-08-16
  License:  Apache-2.0 — see LICENSE
  Part of:  menabò https://github.com/GianniAlessandroni/menabo
============================================================================== -->

# Third-party components

All services run **unmodified** in containers; none are linked into this
repository's code. Versions are pinned in the compose files. Licenses below are
as declared upstream at the time of writing — re-verify on upgrade.

| Component | Pinned version | License | Role |
|---|---|---|---|
| Hermes Agent (Nous Research) | v2026.8.13 | MIT | agent runtime (6 containers) |
| docker-mailserver | 15.1.0 | MIT | Postfix/Dovecot mailserver |
| vLLM (`vllm-openai` images) | cu130-nightly (A) / v0.27.1 (B) | Apache-2.0 | LLM serving |
| Qwen3.6 models (Alibaba/RedHatAI/NVIDIA quants) | see compose | Apache-2.0 | writer / verifier |
| Qwen-Image-2512 | Comfy-Org repackage | Apache-2.0 | illustration model |
| MariaDB | 11.8.8 | GPL-2.0 | wordpress + metrics DBs |
| WordPress | 7.0.4 | GPL-2.0-or-later | CMS |
| WordPress/mcp-adapter | v0.6.1 | GPL-2.0-or-later | MCP door to WordPress |
| SearXNG | 2026.8.16-b2da6b90f | AGPL-3.0 | metasearch (unmodified service) |
| Valkey | 9.1.1 | BSD-3-Clause | SearXNG limiter store |
| Garage (Deuxfleurs) | v2.3.0 | AGPL-3.0 | S3 shared storage (unmodified service) |
| nginx | 1.30.4 | BSD-2-Clause | staging preview |
| ComfyUI (mmartial image) | ubuntu24_cuda13.1-dgx-20260805 | GPL-3.0 (ComfyUI) | image generation |
| comfyui-mcp (artokun) | 0.51.56 | MIT | MCP door to ComfyUI |
| himalaya CLI (pimalaya) | v1.1.0 | MIT | proactive SMTP for agents |
| AWS CLI | debian 13 package | Apache-2.0 | S3 client in agent image |
| aiosmtpd | 1.4.6 | Apache-2.0 | content-filter SMTP proxy |
| PyMySQL | 1.1.1 | MIT | metrics DB driver |
| wp-cli | 2.12.0 | MIT | WordPress provisioning |

AGPL note: SearXNG and Garage are network services used as-is; the AGPL
obligations attach to *their* source (unmodified, publicly available upstream),
not to this repository.
