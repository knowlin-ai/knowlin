## What does this change?

<!-- One or two sentences. Screenshots or a GIF for UI changes. -->

## Checklist

- [ ] `ruff check duckpilot tests tools` and `python -m pytest -q` pass
- [ ] New behaviour has a test (bug fixes: a regression test)
- [ ] Safety rules unchanged (emergency stop, 120 s lock, getting up, paid training, secrets, people – see CONTRIBUTING)
- [ ] Bodies only offer what they can (one rule for brain, skills and interface – see CONTRIBUTING)
- [ ] No secrets, no Pollen model files, no private data
- [ ] Commits are signed off (`git commit -s`, DCO)
