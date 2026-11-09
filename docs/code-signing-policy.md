# Code signing policy

**Status:** applying for free code signing through the SignPath Foundation. Until approval, the Windows installer is
unsigned and Windows shows "unknown publisher" on first start.

Once approved: *Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by
[SignPath Foundation](https://signpath.org).*

## What is signed

- The Windows installer `Knowlin-Setup-<version>.exe`, published on
  [GitHub Releases](https://github.com/knowlin-ai/knowlin/releases).
- Nothing else. The Python package on PyPI (`knowlin`) is published with Trusted Publishing from the same repository.

## How it is built

- Every installer is built by the public GitHub Actions workflow
  [`installer.yml`](../.github/workflows/installer.yml) from a tagged commit of this repository – never on a personal
  machine.
- Before an installer is attached, the workflow installs it, starts Knowlin, checks that the package is complete, and
  runs an update from the previous release.
- Only these CI-built artifacts are submitted for signing. The private key is held by SignPath in a hardware security
  module; this project never has access to it.

## Roles

| Role | Who |
|---|---|
| Committers and reviewers | [@knowlin-dev](https://github.com/knowlin-dev) (maintainer) |
| Approvers (approve each signing request) | [@knowlin-dev](https://github.com/knowlin-dev) |

External contributions are reviewed by the maintainer before merging. All accounts with write access use two-factor
authentication.

## Privacy

Knowlin runs on your computer. It sends data to other systems only when you ask for it or turn it on:

- the AI provider you choose (Anthropic Claude, another provider, or a local model on your PC),
- Hugging Face and GitHub when you download models, policies or Knowlets,
- GitHub once a day to check for updates (can be turned off under Settings → About),
- your phone, if you pair it in your home network.

API keys stay in your operating system's keyring. Faces are recognised only for people you add with their consent, and
only on your PC. Details: [README – Safety and privacy](../README.en.md).

## Other platforms

- macOS and Linux: install with `pipx install knowlin` (Python package, not code-signed).
