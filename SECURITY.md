# Security Policy

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue in **CodeFreedom**, please report it responsibly.

### How to Report

**Option 1: GitHub Private Vulnerability Reporting (Preferred)**
Use GitHub's private vulnerability reporting feature:

1. Go to the repository **Security** tab
2. Click **Report a vulnerability**
3. Follow the prompts to submit your report privately

**Option 2: Email**
Send an email to `nilay.parikh@gmail.com` with the details of the vulnerability.

### Response Timeline

We aim to acknowledge reports within **48 hours**. We will keep you informed of our progress and may ask for additional information.

### What to Include in Your Report

Please include as much of the following information as possible:

- **Description:** A clear description of the vulnerability
- **Steps to reproduce:** Detailed steps to reproduce the issue
- **Impact assessment:** What is the potential impact if exploited
- **Environment:** Python version, OS, Docker version
- **Suggested fix** (if you have one)

## Scope

### In Scope

Vulnerabilities in **CodeFreedom** project code and configurations:

- CLI source code (`src/codefreedom/`)
- Docker configurations
- LiteLLM configuration templates
- Build and CI/CD scripts

### Out of Scope

The following are **not** in scope for CodeFreedom security reports:

- **LiteLLM application code** (upstream bugs) — Report to BerriAI
- **Claude Code CLI** — Report to Anthropic
- **Third-party Python packages** — Report to their respective maintainers
- **Docker base images** — Report to their respective publishers

## Security Best Practices for Users

When using CodeFreedom:

1. Never commit `.env` or `.env.secrets` files containing API keys
2. Use environment variables or a vault solution for sensitive configuration
3. Restrict access to the LiteLLM proxy port (`4000`) in production
4. Keep dependencies updated: `pip install --upgrade codefreedom`
5. Review provider configurations before enabling them
