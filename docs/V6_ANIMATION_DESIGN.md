# PromptMaker 6.0 - Animation expansion design notes

Status: implemented in 6.0.0. Kept as design notes for the Video maker's animation presets; the "Later" section is still open.

## Goal
Expand the existing Video maker with selectable local Wan2GP model/workflow configurations, optional creative LoRA controls and model-specific animation settings. Preserve the working FastWan 5B default. No cloud agents.

## First: validate the installed integration
Inspect the installed Wan2GP version, existing PromptMaker integration and version-matched exported settings/queues. Do not invent JSON schemas or CLI switches. Distinguish model definition present, required files present and workflow tested. Verify installed-version offline support before promising download prevention; current public documentation is not proof of local support. Back up relevant settings and select existing-project test fixtures before implementation.

## Model and workflow picker
- Offer validated local model/workflow presets.
- Show definition availability, required-file readiness and tested status separately.
- Preserve the existing FastWan 5B template and defaults: 1280 x 704, 121 frames, 3 steps.
- Give each configuration its own supported resolution, frame count, steps, guidance and other controls; never copy FastWan defaults universally.
- On model switches, visibly flag or reset incompatible settings and adapters rather than silently carrying them over.
- No guarantee that every model fits 8 GB; no exact VRAM predictions.

## Optional creative LoRA
- Start with one optional creative LoRA and constant strength control.
- Provide None for the creative LoRA, without disabling required acceleration adapters.
- Keep creative and workflow-required adapters distinct in the UI and saved settings.
- Check architecture, model size and image-to-video versus text-to-video compatibility where supported. Names or folders alone do not prove compatibility.
- Do not assume a universal safe strength range or guaranteed quality.
- Defer multiple creative adapters and denoising-step/phase schedules.

## Project defaults, scene overrides and resume
- Project-level animation defaults with explicit per-scene overrides.
- Clearly distinguish inherited values from overrides.
- Store resolved model/workflow identity, template/version, settings, adapters and input references with each clip.
- Resume with recorded settings rather than silently applying changed defaults.
- Preserve old project loading, completed clips and per-scene redo behavior.

## Readiness and safe local execution
- Preflight known missing dependencies, unsupported controls and incompatible combinations.
- No automatic model/dependency downloads, installations or upgrades.
- Verify installed offline protection. If unavailable, report the blocker instead of silently dropping protection or upgrading.
- Dry-run input validation is not proof of complete dependencies or GPU fit.
- Retain existing Forge/ComfyUI VRAM handoff, bounded OOM retry and full logs.
- Preserve completed media on cancel/failure and show a useful next action.

## Later, only after per-model validation
Start/end frames, native continuation and native camera controls may follow where genuinely supported. Last-frame-to-new-start chaining is not native continuation. Do not promise stable identity/geometry or identical output after backend upgrades.

## Implementation sequence
1. Inspect installed versions, exports, current integration and available local configurations.
2. Add configuration storage and compatibility handling while preserving the baseline template.
3. Add model selection, one optional creative LoRA, supported controls and scene overrides.
4. Integrate readiness checks, resolved-settings persistence and resume.
5. Run automated regression checks and real local hardware tests.
6. Prepare documentation and release notes; release v6.0.0 only after validation and approval.

## Acceptance checks
- Original FastWan workflow still works unchanged.
- Existing v5.3 projects load without losing settings or completed media.
- Switching models visibly handles incompatible settings/adapters.
- Missing dependencies fail with a named error and no downloads.
- Creative LoRA None preserves required acceleration adapters.
- Settings and overrides survive reopening and resume correctly.
- Existing SDXL single-main-character face lock remains functional; verified on the release hardware.
- One short supported job succeeds on the actual 8 GB GPU.
- An excessive workload fails boundedly, with a usable UI and preserved completed outputs.
- Image, character/storyboard, library/queue and video-resume regressions pass; remaining modules receive smoke tests.

## Boundaries
No video-editor rewrite, universal model support, automatic identity repair, mandatory cloud dependency or auto-upload.
