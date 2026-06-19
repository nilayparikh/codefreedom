PS C:\Users\nilay> uv tool install codefreedom
Resolved 26 packages in 652ms
Prepared 26 packages in 1.92s
Installed 26 packages in 334ms

+ annotated-types==0.7.0
+ anyio==4.13.0
+ cachebox==5.2.3
+ certifi==2026.5.20
+ charset-normalizer==3.4.7
+ codefreedom==0.1.8
+ deepdiff==9.1.0
+ docker==7.1.0
+ gitdb==4.0.12
+ gitpython==3.1.50
+ h11==0.16.0
+ httpcore==1.0.9
+ httpx==0.28.1
+ idna==3.18
+ orderly-set==5.5.0
+ pydantic==2.13.4
+ pydantic-core==2.46.4
+ python-dotenv==1.2.2
+ pywin32==312
+ pyyaml==6.0.3
+ requests==2.34.2
+ smmap==5.0.3
+ types-pyyaml==6.0.12.20260518
+ typing-extensions==4.15.0
+ typing-inspection==0.4.2
+ urllib3==2.7.0
Installed 2 executables: cf, codefreedom
PS C:\Users\nilay> cf -h
usage: codefreedom [-h] {setup,run,manage} ...

CodeFreedom — Unified CLI for code agents. LLM proxy routing, Docker sandboxing, profile management. All config in ~/.codefreedom.

options:
  -h, --help          show this help message and exit

commands:
  {setup,run,manage}
    setup             One-time setup and configuration (init, config, deinit)
    run               Daily workflows (agent, proxy, tools)
    manage            Occasional maintenance (doctor, update, admin)

---
