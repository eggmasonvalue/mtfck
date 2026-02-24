# Context Artifacts Rule
.context/ artifacts are living documentation for the code. Keep .context/ artifacts in sync with code at all times.

**Artifact Definition:**
| File | Purpose | Update When |
|------|---------|-------------|
| [OVERVIEW.md](OVERVIEW.md) | Project scope and purpose | Dependencies, features change |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Module structure and data flow | Structure changes |
| [CONVENTIONS.md](CONVENTIONS.md) | Code patterns and standards | New patterns established |
| [DESIGN.md](DESIGN.md) | Feature status tracking | Features added/completed |
| [CHANGELOG.md](CHANGELOG.md) | Released changes | Any meaningful change |

**Definition of Done**: A task is complete ONLY when `.context/` artifacts reflect the code changes. Code without context updates is considered BROKEN. 
