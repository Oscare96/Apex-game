# Recovery and architecture decision • 26 November 2026

Recovered main at f6542127651df2543bc486dd4a75db6bf28c52f7. Git reported one remote branch, 15 commits, 15 tracked files, a clean checkout and a successful full object check. Reviewed every tracked file including CI, container, sample config and both handoffs before editing.

| Recovered capability | Evidence |
|---|---|
| Private research API | FastAPI exposes health, identity, episodes and event commentary. Existing routes form a compatibility contract. |
| Driving baseline | For seeds 0 through 999 the controller finished every course at step 20 without a collision. Obstacles sit at y = ±3 and the car travels at y = 0. This measures deterministic execution only. |
| Personality | Two deterministic lines per event and an AI disclosure. No audio, memory, audience input or game recording. |
| Release path | Existing Dockerfile, Compose config, GitHub Actions and a private Cloud Run guide. No deployed revision, live acceptance evidence or credentials in the recovered tree. |
| Baseline checks | Python 3.12.14, six pytest checks passed. Ruff 0.17.6 reported three import-order findings. No Docker engine in the audit workspace. |

## Decision record

| Candidate | What it would provide | Decision |
|---|---|---|
| [Gymnasium Taxi](https://gymnasium.farama.org/v1.2.1/environments/toy_text/taxi/) | Small, CPU-friendly pickup and delivery game with observable states and rewards. [Episode API](https://gymnasium.farama.org/api/env/) distinguishes termination from time limits. | Build the first independent playable show here. Pin the environment, retain action/observation traces and evaluate tabular Q-learning on separate seeds. |
| [Voyager](https://voyager.minedojo.org/) | Minecraft skills, curriculum and code feedback from an LLM. | Revisit for an authorized Minecraft environment. More infrastructure and inference than this first game requires. |
| [Video PreTraining](https://openai.com/index/vpt/) | Minecraft-specific visual imitation learning from large amounts of gameplay. | Evaluate only when a target game, data rights and compute budget warrant a vision policy. |
| [Stable-Retro and other game adapters](https://gymnasium.farama.org/environments/third_party_environments/) | Existing emulator and game interfaces. Game content has separate distribution and capture requirements. | No ROM or retail game is needed for Taxi. Verify the specific game's automation and streaming terms before integrating another title. |

Keep the research service usable independently. Put the show worker, its local policy, recording, broadcast and audience credentials in a dedicated APEX Google Cloud project. Use a bounded process per show, durable single-writer state, FFmpeg and a synthetic stock voice. A continuous process with local media and a disk fits a Compute Engine worker. Retain Cloud Run for the original stateless API. No GPU is required for Taxi.

Use disclosure, captions, media receipts and retries as design ideas from OwnerEasy. Do not share its secrets, databases, channels, voice clones, customer assets or infrastructure. No external service owns a gameplay decision.

## External boundaries

Twitch supports [stream ingest](https://dev.twitch.tv/docs/video-broadcast/) and [EventSub and chat replies](https://dev.twitch.tv/docs/chat/send-receive-messages/). Account setup and acceptance on the actual APEX channel are separate from local tests. [YouTube](https://developers.google.com/youtube/terms/required-minimum-functionality) imposes client and upload requirements. [Instagram](https://developers.facebook.com/docs/instagram-platform/content-publishing/) requires a supported professional account and appropriate permissions. [TikTok](https://developers.tiktok.com/doc/content-sharing-guidelines) requires creator control including a manual privacy selection; its internal account-uploader use case is also excluded. Treat unrestricted hands-off TikTok publishing as blocked. GTA integration has no established automation permission or supported adapter in this repository.
