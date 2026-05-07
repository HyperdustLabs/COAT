# Out-of-tree plugins

The runtime discovers plugins from this directory in addition to
installed packages. M0 ships skeleton folders with templates so you can
copy and start.

```text
plugins/
├── matchers/    # custom MatcherPlugin implementations
├── advisors/    # custom AdvicePlugin implementations
└── storage/     # custom ConcernStore / DCNStore backends
```

See `docs/05-plugins/` (M5) for the contract each plugin type must satisfy.
