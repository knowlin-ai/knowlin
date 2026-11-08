# Good first issues

Small, well-scoped ideas to get started. Comment on the matching GitHub issue before you begin.

1. **A new interface language** – copy `duckpilot/i18n/ui_en.json` to `ui_<lang>.json`, translate, add the language to `SPRACHEN`.
2. **Simple commands in your language** – `brain/fallback.py` understands German and English short commands without an AI model.
3. **More dance gestures** – `TANZGESTEN` in `duckpilot/motion/tanz.py`: suggest gestures from Tricks that dance well.
4. **Tap tempo** – a button on the dance page to tap the beat when the analysis misses it.
5. **Downbeat detection** – the music analysis finds beats but not which one starts the bar (`static/tanz.js`).
6. **Export a dance** – save a choreography as a file to share (later: `.knowlet`).
7. **Keyboard shortcuts overview** – a small dialog listing all shortcuts.
8. **High-contrast check** – run the accessibility tests on new pages and fix findings.
9. **More obstacle course pieces** – new parts for the physics course builder.
10. **A real-duck checklist** – improve the robot checklist in the first-steps assistant with your experience.
11. **Docs: your setup** – a short guide for macOS or Linux.
12. **Sound signature presets** – a few named presets (“baby duck”, “old duck”) for the sound signature.
