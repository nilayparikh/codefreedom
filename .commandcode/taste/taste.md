# Taste (Continuously Learned by [CommandCode][cmd])

[cmd]: https://commandcode.ai/

# configuration

- Eliminate `.env` files entirely; all configuration vars and non-secrets go in YAML files (profiles.yaml, override.yaml, recipe.yaml), and secrets come exclusively from machine environment variables. Confidence: 0.70
- Interpolation of `${VAR}` references is runtime-only (hot-loading); never interpolate and store resolved values to disk — YAML files keep literal `${VAR}` placeholders, resolution happens in-memory every time config is loaded. Confidence: 0.80
