# Contributing to WayTrace

Thanks for your interest in contributing to WayTrace!

## Getting Started

1. Fork the repository
2. Create a feature branch from `develop`:
   ```bash
   git checkout develop
   git checkout -b feature/your-feature
   ```
3. Make your changes
4. Run tests:
   ```bash
   cd backend
   python -m pytest tests/ -v
   ```
5. Open a PR targeting `develop`

**Never PR directly to `main`.** The `main` branch is for stable releases only.

## Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — New feature
- `fix:` — Bug fix
- `refactor:` — Code restructuring without behavior change
- `test:` — Adding or updating tests
- `docs:` — Documentation changes
- `chore:` — Build, config, tooling changes

Each commit should be atomic: 1 feature/fix = 1 commit.

## Branch Structure

| Branch | Purpose |
|---|---|
| `main` | Stable releases |
| `develop` | Integration branch |
| `feature/*` | Feature development |
| `test` | CI / automated tests |
| `front` | Frontend (separate team) |

## Adding a New Extractor

WayTrace uses a plugin-like pattern for data extractors. To add a new one:

1. Open `backend/services/extractor.py`
2. Add your regex pattern at the top of the file:
   ```python
   MY_PATTERN_RE = re.compile(r"your-pattern-here")
   ```
3. Add extraction logic in the `_extract_page()` function:
   ```python
   # --- My New Pattern ---
   for match in MY_PATTERN_RE.finditer(raw_text):
       value = match.group(1)
       _update_entity(
           accum["my_new_field"],
           value,
           month,
           {"value": value},
       )
   ```
4. Add the new field to the `accum` dict in `extract_all()`
5. Add the output formatting in the return statement of `extract_all()`
6. Write tests in `backend/tests/test_extractor.py`:
   - At least 5 valid matches
   - At least 5 false positives that should NOT match
7. Update `docs/API.md` with the new field

## Code Style

- Python 3.11+
- Type hints encouraged
- Use `loguru` for logging
- Use `selectolax` for HTML parsing (not BeautifulSoup)

## Legal

By contributing, you agree that your contributions will be licensed under the MIT License.
