# APEX channels and live acceptance

All endpoints act on accounts controlled by APEX. The code has real provider adapters. Current evidence covers encoded media and protocol tests. Buzz must record actual dashboard and API receipts before enabling a platform on the recurring shift. An encoded packet or HTTP ingest connection does not prove a viewer could watch.

## Provision credentials

Use an APEX-owned OAuth application and the corresponding creator account. An OwnerEasy token, voice, customer account or project must never be substituted. Register only the callback URIs actually used for interactive OAuth setup.

| Integration | Required account setup |
|---|---|
| Twitch live | Get the APEX channel's primary stream key in Creator Dashboard. The first transport test uses Twitch's bandwidth-test flag. The normal Twitch ingest publishes to that channel. |
| Twitch chat and title | Register the app with Twitch. Complete the user authorization-code flow as the **APEX broadcaster**. Request `user:read:chat`, `user:write:chat`, and `channel:manage:broadcast` only if enabling title updates. Exchange the authorization code at Twitch's token endpoint, retain the refresh token, and obtain the numeric broadcaster ID from token validation. The worker validates the client ID, subject and scopes and persists rotated tokens with mode 0600. [Twitch OAuth](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/) · [Token validation](https://dev.twitch.tv/docs/authentication/validate-tokens/) · [Chat](https://dev.twitch.tv/docs/chat/authenticating/) |
| YouTube live | Enable live streaming for the APEX channel. Create an encoder broadcast in Live Control Room, choose **private** for acceptance, check the visibility, enable auto-start/auto-stop if desired, and copy its RTMPS stream key. Broadcast scheduling and event creation stay in Live Control Room for this release. [Encoder setup](https://support.google.com/youtube/answer/2907883) |
| YouTube highlights | Enable YouTube Data API v3 in the APEX Google project, configure the consent screen and register an OAuth client. Use the installed-app authorization-code flow on a trusted workstation with offline access and the `youtube.upload` and `youtube.readonly` scopes. Sign in to the APEX channel and retain its refresh token and immutable channel ID. Check project verification/audit, quota, channel eligibility and token expiry for the deployment's intended visibility. [Google OAuth](https://developers.google.com/youtube/data/guides/auth/installed-apps) · [Resumable uploads](https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol) · [Upload requirements](https://developers.google.com/youtube/terms/required-minimum-functionality) |
| Instagram Reels | This adapter uses **Instagram API with Facebook Login**. Link the APEX professional Instagram account to a Facebook Page. Use Meta's app flow for that Page and obtain its Page access token, Page ID and linked Instagram business account ID. Verify your app version, mode, roles and required `instagram_basic`, `instagram_content_publish` and Page read/list permissions for this login path. Use a test professional account with app access first. Configure token renewal for that Page before enabling recurring posts. [Meta publishing guide](https://developers.facebook.com/docs/instagram-platform/content-publishing/) |
| TikTok | Export a vertical clip for creator review. TikTok's Direct Post guidelines exclude internal account-uploader tools and require creator choices per post. APEX does not have an unattended TikTok poster. [Direct Post rules](https://developers.tiktok.com/doc/content-sharing-guidelines) |

Store only configured providers in one JSON secret named `apex-accounts`. This schema shows **field names and placeholders**. The stream key under each provider must belong to the selected channel. Choose the YouTube audience designation, title, description and privacy explicitly. Optional title and description override generated copy. The disclosure stays on the video and in its description.

```json
{
  "twitch_stream_key": "<APEX Twitch stream key>",
  "youtube_stream_key": "<APEX YouTube stream key>",
  "twitch": {
    "client_id": "<client ID>",
    "client_secret": "<app secret>",
    "refresh_token": "<broadcaster refresh token>",
    "broadcaster_id": "<numeric Twitch user ID>"
  },
  "youtube": {
    "channel_id": "<actual UC channel ID>",
    "client_id": "<OAuth client ID>",
    "client_secret": "<OAuth client secret>",
    "refresh_token": "<channel refresh token>",
    "privacy": "private",
    "made_for_kids": false
  },
  "instagram": {
    "account_id": "<numeric IG professional account ID>",
    "page_id": "<numeric Facebook Page ID>",
    "page_access_token": "<Page access token>",
    "api_version": "<supported app version such as v25.0>"
  }
}
```

Create the secret from a protected local file outside the checkout or from Secret Manager's UI. Run from the operator's Cloud Shell with the project variables from the deployment guide.

```bash
gcloud secrets create apex-accounts --replication-policy=automatic --project="$PROJECT_ID"
read -rp 'Path to protected JSON outside the repository: ' ACCOUNTS
gcloud secrets versions add apex-accounts --data-file="$ACCOUNTS" --project="$PROJECT_ID"
gcloud secrets add-iam-policy-binding apex-accounts --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor --project="$PROJECT_ID"
```

On the VM, verify `gcloud version`. If the VM image lacks it, install the [Google Cloud CLI Debian package](https://cloud.google.com/sdk/docs/install#deb). Set the **specific accepted version number** as `APEX_SECRET_VERSION` in `/etc/apex/worker.env`. At each start the launcher obtains that version using the VM identity, mounts it read-only, and enables outbound networking. The checkout and shell history contain no credential values.

## Exercise one capability at a time

Keep the daily timer stopped during channel acceptance. Start with `"fares":1`, `"publish":[]`, `"twitch_title":false`, and change only the setting under test in `/etc/apex/shift.json`. On the VM, use the following wrapper for one-off shift IDs. A reused ID must have the same configuration and destination accounts.

```bash
sudo systemctl stop apex-shift.timer
sudo bash -c 'set -a; . /etc/apex/worker.env; set +a; exec bash /opt/apex/deploy/run-worker shift --id "$1"' _ twitch-bandwidth-01
```

Use that command pattern with the corresponding unique test ID.

1. **Twitch bandwidth.** Set `broadcast` to `twitch-test` before running `twitch-bandwidth-01`. In Twitch Inspector confirm an incoming test, correct resolution, audio, stable frame rate, and that public viewing stayed off. Record the inspector evidence. Inspect a local recording for synchronized words and AI disclosure.
2. **YouTube live.** Set `broadcast` to `youtube`, leave publishers empty, use a new ID. Confirm the destination event is private in Live Control Room before starting. Verify picture, speech, disclosure, end-of-stream and the archived event's actual privacy. Mark the first public broadcast as a separate operator decision.
3. **Twitch audience.** From the VM run `sudo systemctl start apex-chat`. From a second permitted account send `!apex`, then `!game` and `!stats` at least 60 seconds apart. Confirm the replies identify APEX, cite the actual stored record, and appear only once. Within the cooldown verify a second command is suppressed. Try `apex, how did you learn?` or `!joke` after the cooldown. Unrecognized chat and messages from APEX itself should get no reply. Stop chat after the test or enable it with `sudo systemctl enable --now apex-chat` for the pilot. Leave sufficient time after a startup failure to respect provider rate limits.
4. **Twitch management.** On the test APEX channel set `twitch_title` to true in an offline-broadcast shift with a new ID. Confirm the fixed AI-disclosed title in the channel dashboard. This changes channel metadata.
5. **YouTube post.** Set `broadcast` to `off`, `twitch_title` to false and `publish` to `["youtube"]`. Confirm the secret selects private visibility. Run a new shift. Record its remote video ID, channel, playback, disclosure, requested versus actual visibility and processing status in Studio. Rerun the same shift and require the same ID with one video. A provider receipt proves acceptance for upload; viewing in Studio proves processing and visibility.
6. **Instagram post.** Use only an authorized test professional account. Reels publishing can make the media visible on that account. Set `publish` to `["instagram"]` and use a new shift ID. Confirm the matching Page/IG account, media ID or published container, caption, sound and Reel in the app. Rerun the same ID and require one Reel. Allow the processing check up to five minutes. The worker uploads video bytes directly to Meta.
7. **Pilot schedule.** Select just the accepted broadcaster and publishers. A shift features one game title, rotating the title across scheduled dates. It selects a winning episode first, then the best score within the featured title, and sends that highlight once per enabled destination. Review the platform quotas, spend and cadence. Start the timer with `sudo systemctl enable --now apex-shift.timer`. The default broadcasts only individual bounded shifts. Public GTA play, cross-platform replies, and claims of 24/7 live operation are outside current evidence.

## Recover a delivery

The scheduled service retries a failed shift after 15 minutes, with at most three starts in six hours. After the window, rerun the original shift ID with its original config, credential account IDs and persistent state. The upload journal respects provider Retry-After deadlines across restarts. YouTube probes the saved resumable session for its offset or final receipt. Meta reuses the original container and queries its processing status. If a previous Meta publish is ambiguous, the system stops before a second attempt; a confirmed `PUBLISHED` container is an acceptable recovery receipt. Inspect rate limits, expiry, permission errors and stalled sessions in the provider dashboard. A lost receipt, expired upload session or lost snapshot needs reconciliation before starting a fresh upload. Never delete a delivery journal to clear an error without checking the destination. The two publishers advance independently.

**Emergency stop.** Disable the timer, stop chat, stop any running shift container or service, then end the event in the provider dashboard and rotate the stream key if required. Inspect the retained live shift journal before retrying. Revoke the application grants from each account if access must end. For a planned Twitch reauthorization, stop both services, save the protected token cache for incident review, replace the secret with the new grant, and move the old cache out of the live state directory before restarting. The local cache contains the latest rotated refresh token.
