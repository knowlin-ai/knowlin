# Security

Knowlin / duckpilot runs on your PC, opens a local web interface and – if you allow it – a phone remote and an MCP
server. It can load **Knowlets** (shared packages) from files or Hugging Face.
Please report security problems **privately**, not as a public issue.

**How:** use GitHub's “Report a vulnerability” (Security → Advisories) on this repository. If that button is
missing, open an issue titled “Security contact” – **without any details** – and we will get in touch privately. We aim to answer within a
week and to ship a fix for confirmed problems as a patch release (0.x.y). Maintainer: @knowlin-dev.

Especially interesting:

- ways to reach the interface, the phone remote or MCP from outside your PC or home network without pairing,
- ways to read keys or secrets from the vault, logs, reports or the browser,
- ways to bypass the emergency stop, the lock after it or the two-click rule for paid training,
- ways to see people data from a phone,
- Knowlets that get past the package check (`duckpilot/knowlets.py`): files outside the package, code, oversized
  archives, or texts that end up as instructions,
- ways to upload to Hugging Face without the second click, or publicly when “private” was chosen.

Problems with someone's behaviour (Code of Conduct) can go the same private way – start the title with
“Conduct:”.

Never include real keys, recordings of people or private data in a report.
