# Optional private research API on Cloud Run

Use this only for the original driving simulation and commentary API. The show worker uses the Compute Engine guide. In the dedicated project, record the accepted release SHA, select a region, and check out that exact commit before building. Use an operator authorized for Cloud Build, Artifact Registry, Cloud Run and service account impersonation. Grant the project's actual build identity write access to the APEX image repository if required by your build policy.

```bash
: "${PROJECT_ID:?Set the dedicated APEX project}"
: "${REGION:?Set the Cloud Run region}"
: "${RELEASE:?Set the verified commit SHA}"
test "$(git rev-parse HEAD)" = "$RELEASE" || exit 1
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com --project="$PROJECT_ID"
gcloud artifacts repositories create apex-images --repository-format=docker --location="$REGION" --project="$PROJECT_ID"
gcloud iam service-accounts create apex-api --project="$PROJECT_ID"
API_SA="apex-api@$PROJECT_ID.iam.gserviceaccount.com"
gcloud secrets create apex-api-key --replication-policy=automatic --project="$PROJECT_ID"
python3 -c 'import secrets,sys; sys.stdout.write(secrets.token_urlsafe(48))' | gcloud secrets versions add apex-api-key --data-file=- --project="$PROJECT_ID"
gcloud secrets add-iam-policy-binding apex-api-key --member="serviceAccount:$API_SA" --role=roles/secretmanager.secretAccessor --project="$PROJECT_ID"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/apex-images/research:$RELEASE"
gcloud builds submit --tag="$IMAGE" --project="$PROJECT_ID" .
gcloud run deploy apex-research --image="$IMAGE" --service-account="$API_SA" --set-secrets=APEX_API_KEY=apex-api-key:1 --no-allow-unauthenticated --min-instances=0 --max-instances=1 --memory=512Mi --cpu=1 --concurrency=5 --region="$REGION" --project="$PROJECT_ID"
```

Reuse existing matching resources on subsequent releases. For an existing secret select the verified current version rather than assuming version 1. Give the smoke-test identity Cloud Run Invoker on this service and access to the selected API secret.

```bash
URL=$(gcloud run services describe apex-research --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)')
IDENTITY=$(gcloud auth print-identity-token)
KEY=$(gcloud secrets versions access 1 --secret=apex-api-key --project="$PROJECT_ID")
curl -fsS -H "Authorization: Bearer $IDENTITY" "$URL/health"
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $IDENTITY" "$URL/identity"
curl -fsS -H "Authorization: Bearer $IDENTITY" -H "X-Apex-Key: $KEY" "$URL/identity"
curl -fsS -H "Authorization: Bearer $IDENTITY" -H "X-Apex-Key: $KEY" -H 'Content-Type: application/json' --data '{"seed":7}' "$URL/episodes"
unset KEY IDENTITY
```

Expect health in simulation mode, HTTP 401 without the app key, an explicit AI disclosure with it, and a successful bounded driving episode. Save the revision and check its IAM policy for accidental unauthenticated grants. Roll back by selecting an actual previously accepted revision from the list and updating traffic.

```bash
gcloud run revisions list --service=apex-research --region="$REGION" --project="$PROJECT_ID"
read -rp 'Previously verified revision: ' PREVIOUS
gcloud run services update-traffic apex-research --to-revisions="$PREVIOUS=100" --region="$REGION" --project="$PROJECT_ID"
```
