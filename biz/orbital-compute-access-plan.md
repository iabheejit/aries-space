# Orbital Compute Access Plan

**Date:** 2026-08-15
**Goal:** Run the same checksum-pinned Aries workload and input on a terrestrial cloud node and a real in-orbit compute node, with enough execution evidence to compare latency, output reduction, and energy honestly.

## Recommended Path

### 1. Ground Baseline — Start Now

Use AWS for the canonical terrestrial run because Sentinel-2 L2A is available from the Registry of Open Data on AWS without an AWS account:

- Bucket: `s3://sentinel-s2-l2a/`
- Region: `eu-central-1`
- Access: `aws s3 ls --no-sign-request s3://sentinel-s2-l2a/`
- STAC: `https://sentinel-s2-l2a-stac.s3.amazonaws.com/`

Run the same arm64-compatible container on a pinned AWS Graviton instance and, optionally, an Azure arm64/CPU VM. Record instance type, region, vCPU/RAM, image digest, workload/model digest, input checksum, wall/inference time, and cloud billing inputs. Cloud power remains estimated unless the provider supplies attributable energy telemetry.

AWS Ground Station and Azure orbital/ground-station services are ground infrastructure; they do not by themselves provide onboard compute.

### 2. TakeMe2Space OrbitLab — Best India Route

Primary source: `https://www.tm2.space/orbitlab`

- Free development sandbox is advertised now.
- Supports native applications, Docker containers, and ONNX models.
- Developer access is exposed through gRPC from Python, C++, Node.js, or other languages.
- MOI hardware is advertised as NVIDIA Jetson Orin NX, 117 TOPS, 16 GB LPDDR5, 2 TB storage, and 10–55 W compute range.
- Public pricing advertises $4/minute for live satellite tasking and $200/orbit for academia.
- MOI-1A is publicly scheduled for October 2026. Sandbox validation is immediate; real-orbit scheduling must be confirmed contractually.

**Action:** register at `https://orbitlab.tm2.space/`, port the Aries workload to its Docker/ONNX interface, and request a GHRCE/TDIP research slot on MOI-1A. Contact: `info@tm2.space`.

### 3. D-Orbit Space Cloud + SkyServe — Best Flight-Proven Route

Primary sources:

- `https://dorbit.space/advanced-services/`
- `https://www.skyserve.ai/`

D-Orbit advertises Software In-Orbit Demonstration using Linux, TensorFlow, PyTorch, and virtualized containers on ION Satellite Carrier onboard computers. ION launches multiple times per year and provides power, uplink, downlink, memory, and mission operations. SkyServe publicly reports successful onboard AI collaborations with D-Orbit and JPL.

**Action:** send a joint software-in-orbit demonstration request to D-Orbit and SkyServe. Position Aries as a neutral benchmark workload, not a competing onboard-execution platform. Ask for an existing ION compute slot before considering a new hosted-payload launch.

### 4. EDGX STERNA — In Orbit, Partnership Access

Primary sources:

- `https://www.edgx.space/product/sterna`
- `https://www.edgx.space/contact`

STERNA is advertised as flight-proven, NVIDIA-powered compute up to 157 TOPS, with two hosted units reported in orbit in April 2026. No public self-service developer portal was found.

**Action:** contact `info@edgx.space` for a software experiment on an operational hosted unit. Treat this as B2B integration until they confirm container/model upload and telemetry access.

### 5. Orbitworks Virtual Mission — Strong Future Alternative

Primary source: `https://orbitworks.space/mission-models/virtual-mission/`

Orbitworks explicitly offers software, analytics, and AI deployment to onboard compute without customer-owned satellite hardware. Public material does not specify a self-service API, flight slot, hardware details, or current operational availability.

**Action:** request a Virtual Mission quote and timeline, but do not place it on the critical path until an operational node and interface are confirmed.

## Non-Negotiable Experiment Contract

An orbital run counts as Aries evidence only if the provider supplies:

1. Exact workload/model artifact digest and immutable runtime/container identifier.
2. Exact input checksum, or a documented onboard sensor product whose corresponding ground copy is supplied unchanged.
3. Hardware identity, CPU/GPU mode, memory limit, software stack, and throttling configuration.
4. Start/end monotonic timestamps and inference duration from the execution node.
5. Input and output byte counts plus output checksum.
6. Power evidence: measured average/peak watts and joules where available, with source (`tegrastats`, board telemetry, external meter). If unavailable, energy remains provider-estimated and is labeled accordingly.
7. Pass/orbit ID, upload/downlink windows, retries, failures, and execution logs.
8. Permission to publish aggregated benchmark numbers and an explicit limitations statement.

Without items 1–5, the run is a demonstration but not a valid cross-target benchmark. Without item 6, latency and data-reduction results can be measured, but energy remains estimated.

## Test Package To Offer Providers

- Architecture: arm64 Docker image first; ONNX package second.
- Initial imagery workload: deterministic NDVI summary or cloud mask on one small Sentinel-2 crop.
- Input size: 50–250 MB crop, checksum-pinned.
- Output: canonical JSON plus optional compressed mask, both checksum-pinned.
- Runtime budget: under five minutes, under 8 GB RAM.
- Network: no outbound network during execution.
- Repeat count: at least 10 runs on the same input for median/p95 latency.
- Comparison targets: AWS Graviton terrestrial node, provider sandbox, real orbital node.

NDVI is the best first flight workload because it is deterministic, model-free, easy to verify independently, and avoids model licensing or accelerator compatibility disputes. Ship/cloud ONNX workloads follow after the execution protocol is proven.

## Outreach Ask

> Aries Space is building a neutral orbit-vs-ground workload benchmark for a DoT/TCoE NTN edge-compute pilot with GHRCE. We have a checksum-verifiable Docker/ONNX harness running on PostgreSQL/MinIO and terrestrial arm64 targets. We seek one sandbox integration and one real in-orbit execution slot for a deterministic Sentinel-2 workload, with node timing, output checksums, and power telemetry where available. We will clearly distinguish measured, estimated, and simulated results and can share an anonymized benchmark report with the provider.

## Decision

Proceed in parallel:

1. Establish the AWS Graviton + Sentinel-2 ground baseline now.
2. Register and integrate with OrbitLab sandbox now; request an October MOI-1A research slot.
3. Send D-Orbit/SkyServe and EDGX requests for an earlier operational in-orbit slot.
4. Do not buy/build a hosted hardware payload until software-slot options are exhausted.
