# Profile Maintenance

Update one concrete target surface at a time.

1. Read the current official documentation for the exact surface.
2. Identify the smallest capability claims affected by the change.
3. Record official HTTPS sources and their coverage.
4. Set `reviewed_at` to the actual review date.
5. Use `unknown` for silence or ambiguity; do not copy a claim from another
   surface owned by the same vendor.
6. Update rules only when the capability vocabulary or semantics changed.
7. Add or update tests that demonstrate the effect on compatibility grades.
8. Run profile loading, linting, type checking, tests, and package-data checks.

Documentation proves a documented contract, not observed runtime behavior.
Store runtime evidence separately and bind it to the artifact revision and
client version.
