# Taste (Continuously Learned by [CommandCode][cmd])

[cmd]: https://commandcode.ai/

# configuration

- Eliminate `.env` files entirely; all configuration vars and non-secrets go in YAML files (profiles.yaml, override.yaml, recipe.yaml), and secrets come exclusively from machine environment variables. Confidence: 0.80
- Interpolation of `${VAR}` references is runtime-only (hot-loading); never interpolate and store resolved values to disk — YAML files keep literal `${VAR}` placeholders, resolution happens in-memory every time config is loaded. Confidence: 0.80
- Config resolution chain (lowest to highest priority): profiles.yaml → recipe.yaml → override.yaml → CF_CLI_*. No bare os.environ lookups — bare machine env vars are NOT in the chain, only CF_CLI_* prefix-stripped vars with the prefix removed. Confidence: 0.85
- `vars:` sections from recipe.yaml and override.yaml are dynamic key-value pairs that feed into the interpolation context alongside CF_CLI_* overrides, avoiding the need for bare environment variables for non-secret config values. Confidence: 0.75
