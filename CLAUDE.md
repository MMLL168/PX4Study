# PX4-Autopilot

Safety-critical C/C++ flight control firmware for autopilots, plus SITL
simulation and Python tooling.

- **Commits:** use the `/commit` skill. Conventional commit format with
  topic-based scope: `type(scope): description`.
- **Pull requests:** use the `/pr` skill.
- **No Claude attribution** — no `Co-Authored-By: Claude`, no "Generated
  with Claude Code" footer.
- **Style:** run `make format` on changed C/C++ before committing; CI
  enforces `make check_format`.
- **學習筆記：** 任何觀念解釋、架構說明、除錯技巧、原理分析等學習相關內容，
  一律記錄到 `Study/learn.md`。
- **修改記錄：** 每次對程式碼、設定檔、板級移植等進行修改，
  都必須在 `Study/devlog.md` 補上一筆記錄，格式為
  `## [YYYY-MM-DD HH:MM] 標題` + 問題、原因、處理方式三段。
