# Simple onboarding implementation plan

Goal: paste a key and continue without operating the local service manually.
Architecture: keep CEP host/backend interfaces; share one in-flight readiness
promise in panel/js/app.js. Reuse Setup for first-use onboarding and AI settings.
Tech stack: existing plain JavaScript, HTML/CSS and Node tests.
Spec: ../specs/2026-11-15-simple-onboarding.md

Constraints: no paid test requests, secrets remain local, no new dependencies.
Review focus: simultaneous startup/save; service failure; credential-write failure;
returning provider choice; navigation while background connection completes.

- [x] Extend panel/tests/test_provider_setup.js with the acceptance cases and run red.
- [x] Implement coalesced startup, safe save/retry, first-use routing and persistence.
- [x] Simplify panel/index.html, hide diagnostic/account details and update guides.
- [x] Run focused tests, complete release checks and narrow browser verification.
- [x] Install only changed panel files with backup; verify live readiness without exposing keys.
- [x] Review, commit and push. Keep unsigned publication policy unchanged.


Validation: 14 focused onboarding tests pass. Full scripts/check_release.py
passes with CAPFORGE_TEST_MACOS_APP=/private/tmp/capforge-onboarding-build/CapForge.app.
Fresh universal native app built and verified. Browser demo plus mocked host
checked at 500px viewport: no horizontal overflow; saved provider restored.
Independent review caught retry reconnecting without saving; reproduced RED,
fixed GREEN with a dedicated regression test. Existing Windows console launcher
is unchanged; its startup is now automatic but may still show its console.

Installed panel and help files backed up and updated locally. Authenticated
readiness confirms installed v0.3.3 service, audio support and configured
ElevenLabs. No real credential write or paid transcription was performed.
The open AE panel must be closed/reopened to load updated JavaScript; real
user-driven first-use acceptance remains to be confirmed after reload.
