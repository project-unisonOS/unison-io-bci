# Contributing to Project Unison

Thank you for your interest in improving Project Unison.  
This document applies to all repositories under the **project-unisonOS** organization.

---

## Overview
Project Unison is an experimental, modular platform that merges context-aware AI with open computing principles.  
All contributions — code, documentation, research, or accessibility testing — help shape a more inclusive and adaptive computing future.

---

## Development Workflow

### Branching Model
- **`main`** – stable, production-ready branch.  
- **`dev`** – active development integration branch.  
- `feature/*` or `fix/*` – short-lived branches for specific changes.

### Workflow Summary
1. Fork the repository and create your feature branch:  
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Make your changes.
3. Validate builds and run tests locally or with Docker Compose.
4. Commit using clear messages:
   ```bash
   git commit -m "Add: short description of change"
   ```
5. Push your branch and open a Pull Request against `dev`.

---

## Commit and PR Guidelines
- Use clear, imperative commit titles (e.g., *“Add context update handler”*).  
- Keep PRs focused; multiple small PRs are preferred over one large one.  
- Include a concise description and link related issues.  
- Ensure CI checks pass before requesting review.

---

## Documentation Standards
- All documentation must follow **WCAG 2.2 AA** accessibility standards.  
- Use semantic Markdown headings (`#`, `##`, etc.) and plain-language summaries.  
- Add **alt text** for all images and diagrams.  
- Keep diagrams and references versioned in the `/docs` or `/specs` folder.  
- Update the `user-journeys` folder when adding new behavioral flows.

---

## Accessibility Commitments
Unison’s foundation is inclusive design.  
If you introduce features that affect human interaction — input, display, or policy behavior — confirm that:
- Keyboard and screen reader use cases are supported.  
- Default color palettes meet contrast ratios.  
- Audio or visual indicators have redundant cues.

---

## Issue Reporting
- Use GitHub Issues for bugs, documentation gaps, or feature requests.  
- Use the `enhancement`, `bug`, or `accessibility` labels where relevant.  
- When reporting, include reproduction steps and environment details.

---

## Communication
Discussion happens primarily through GitHub Issues and Pull Requests.  
For sensitive or private matters (e.g., conduct reports), use the contact email in the [Code of Conduct](CODE_OF_CONDUCT.md).

---

## License
All contributions are governed by the repository’s LICENSE file.  
By submitting a Pull Request, you agree your contribution will be released under the same license.
