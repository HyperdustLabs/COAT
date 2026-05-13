# Example matcher plugin

Replace the `apply` function with your matcher. Register the package via
its `pyproject.toml` entrypoint:

```toml
[project.entry-points."opencoat_runtime.matchers"]
my_matcher = "my_matcher.module:MyMatcher"
```
