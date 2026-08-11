# ACE-Step 1.5 Smoke Test Report

## Goal

Validate the local music-generation path by producing and retrieving one
audio file from ACE-Step 1.5 on the CUDA-capable `agpc` node. Quality tuning,
service operation, and application integration were outside this test.

## Environment and installation

- `agpc` was reachable through the managed Ansible channel.
- The node provides a Quadro RTX 8000 with 48 GB VRAM, CUDA 13.1 driver
  support, Python 3.12.3, Git, and uv.
- Existing graphics and ComfyUI processes used about 0.9 GB VRAM before the
  test, leaving sufficient capacity for inference.
- ACE-Step 1.5 was cloned into its own environment and installed with `uv
  sync`.
- The main ACE-Step model package was downloaded. It includes the Turbo DiT,
  VAE, text encoder assets, and the 1.7B LM.

## Generation result

- The Turbo DiT model was initialized successfully on CUDA.
- A single 10-second instrumental electronic-music request was submitted with
  a fixed seed and eight Turbo inference steps.
- The job completed successfully and produced a stereo 48 kHz, 16-bit PCM WAV
  file. The retrieved file is approximately 1.8 MB and reports an exact
  duration of 10 seconds.
- The reported end-to-end generation time was about 2.5 seconds for one song.

## Runtime note

The RTX 8000 is a Turing-generation GPU, so FlashAttention was unavailable.
ACE-Step automatically fell back to the PyTorch CUDA backend for the LM and
still completed the generation successfully. Peak inference allocation was
well within available VRAM, and GPU utilization returned to idle after the
test.

## Cleanup and follow-up

The temporary loopback-only API process used for this test was stopped after
the file was retrieved. No persistent service, desired-state registration, or
application integration was added.

The remaining acceptance check is human listening: play the retrieved WAV and
confirm that it is audible music.
