# Google Cloud deployment — Buzz runbook

## Prerequisites
- A **dedicated** Google Cloud project for APEX; never reuse OwnerEasy production resources.
- Billing linked and budget notifications configured (budgets are **not** hard spending caps).
- `gcloud` CLI authenticated to the intended account, Docker installed locally, and permission to enable services, create Artifact Registry repositories and deploy Cloud Run.
- Choose a region with Cloud Run and Artifact Registry support; example below uses `us-central1`.
- Review IAM roles and organizational policies before applying. Do not use project-wide Owner roles for the runtime.

## 1. Select project (Buzz must replace placeholders with verified values)
```bash
export PROJECT_ID='REPLACE_WITH_VERIFIED_APEX_PROJECT_ID'
export REGION='us-central1'
export REPO='apex-images'
export SERVICE='apex-research'
gcloud config set project "$PROJECT_ID"
gcloud config get-value project
```
Stop if project does not match the dedicated APEX project.

## 2. Enable required APIs and create image repository
```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com
# Run only if repository does not already exist:
gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION" --description='APEX research images'
```

## 3. Create an API secret
```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```
Store the generated value securely; do not paste it in tickets, commits, logs, or chat. In Secret Manager, create a secret named `apex-api-key`, add its value as version 1, and grant **only the Cloud Run runtime service account** `roles/secretmanager.secretAccessor` on that secret. Do not grant it to all users.

## 4. Build image and deploy
```bash
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/apex:0.1.0"
gcloud builds submit --tag "$IMAGE" .
```
Create a dedicated runtime service account named `apex-runtime` (if absent), then grant the secret accessor role on the individual secret. Deploy privately:
```bash
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --service-account "apex-runtime@$PROJECT_ID.iam.gserviceaccount.com" \
  --set-secrets APEX_API_KEY=apex-api-key:1 \
  --no-allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --memory 512Mi \
  --cpu 1 \
  --concurrency 5
```
This is a *private* research API. Invoke with a Google identity token and `X-Apex-Key` (two separate protections). Never expose the API key in a public frontend. For a production rollout, move from a static shared API key to scoped identities and service-to-service IAM.

## 5. Verify and rollback
```bash
gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)'
gcloud run revisions list --service "$SERVICE" --region "$REGION"
```
Use authenticated requests to verify `/health` and `/episodes`. Record the revision and test results. To roll back, route traffic to a previously verified revision with `gcloud run services update-traffic` after reviewing the target revision. Do not automatically promote a failed deployment.

## Cost and security
- Cloud Run, Cloud Build, Artifact Registry, Secret Manager and egress can all incur charges.
- Set budget alerts before deployment; monitor actual charges and disable unused resources.
- No GPU, streaming, public ingress, or social platform permissions are configured by this runbook.
- Configure log retention and restrict deployment privileges; do not store secrets in source control.