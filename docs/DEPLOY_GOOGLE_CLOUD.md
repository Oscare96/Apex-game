# Buzz deployment guide

Deploy the creator worker on one dedicated Google Compute Engine VM. Its disk holds policies, replays, verified media, delivery journals and the Twitch token cache. The original stateless research API has a separate [Cloud Run guide](RESEARCH_API.md). The worker does not need the API.

## 1. Select the target

Use Google Cloud Shell in an APEX-only billed project. Record the project ID, operator, approved budget, region, zone, commit SHA and GitHub CI run. Set a budget and notification recipient in Billing. A budget notification does not stop resources. Price the VM, disk, NAT, snapshots, and outbound video for the chosen region and broadcast hours. The initial pilot uses two vCPUs and no GPU.

```bash
read -rp 'Dedicated APEX project ID: ' PROJECT_ID
read -rp 'APEX region: ' REGION
read -rp 'Zone in that region: ' ZONE
read -rp 'Verified 40-character Git commit: ' RELEASE
[[ "$RELEASE" =~ ^[a-f0-9]{40}$ ]] || exit 1
gcloud projects describe "$PROJECT_ID" --format='table(projectId,name,projectNumber)'
gcloud compute zones describe "$ZONE" --project="$PROJECT_ID" --format='value(region.basename())'
```

Confirm the project and zone before provisioning. The operator needs rights for Compute, VPC/NAT, project service accounts, API enablement, OS Admin Login and IAP TCP forwarding. Give the VM its own service account. It needs no project-wide role. Add secret access only when testing external accounts.

## 2. Create the private VM

Run in Cloud Shell. These are first-install commands. For a resumed install, describe the named resource and reuse it after confirming its properties. Substitute an available, non-overlapping subnet CIDR if the project uses a connected network. Leave OwnerEasy networks disconnected.

```bash
gcloud services enable compute.googleapis.com iam.googleapis.com iap.googleapis.com secretmanager.googleapis.com --project="$PROJECT_ID"
gcloud iam service-accounts create apex-worker --display-name='APEX worker' --project="$PROJECT_ID"
SA="apex-worker@$PROJECT_ID.iam.gserviceaccount.com"
gcloud compute networks create apex-net --subnet-mode=custom --project="$PROJECT_ID"
gcloud compute networks subnets create apex-subnet --network=apex-net --range=10.82.0.0/24 --enable-private-ip-google-access --region="$REGION" --project="$PROJECT_ID"
gcloud compute routers create apex-router --network=apex-net --region="$REGION" --project="$PROJECT_ID"
gcloud compute routers nats create apex-nat --router=apex-router --region="$REGION" --auto-allocate-nat-external-ips --nat-all-subnet-ip-ranges --project="$PROJECT_ID"
gcloud compute firewall-rules create apex-iap-ssh --network=apex-net --allow=tcp:22 --source-ranges=35.235.240.0/20 --target-service-accounts="$SA" --project="$PROJECT_ID"
gcloud compute instances create apex-worker --zone="$ZONE" --project="$PROJECT_ID" \
  --machine-type=e2-standard-2 --image-family=debian-12 --image-project=debian-cloud \
  --subnet=apex-subnet --no-address --service-account="$SA" --scopes=cloud-platform \
  --metadata=enable-oslogin=TRUE --boot-disk-size=30GB --boot-disk-type=pd-balanced \
  --create-disk=name=apex-state,device-name=apex-state,size=40GB,type=pd-balanced,auto-delete=no
gcloud compute ssh apex-worker --zone="$ZONE" --project="$PROJECT_ID" --tunnel-through-iap
```

The subnet has outbound NAT and the VM has no public IP. The only project-created ingress rule above is SSH from IAP to the worker. [Google IAP instructions](https://docs.cloud.google.com/compute/docs/connect/ssh-using-iap) · [Google NAT instructions](https://docs.cloud.google.com/nat/docs/set-up-manage-network-address-translation)

## 3. Prepare durable state and install the verified release

Run on the VM. Check the device name, size, filesystem and mount points. Only format a newly provisioned, empty `apex-state` disk. On recovery, mount the existing filesystem.

```bash
sudo apt-get update
sudo apt-get install -y docker.io git ca-certificates curl gnupg
sudo systemctl enable --now docker
DEVICE=/dev/disk/by-id/google-apex-state
lsblk -f "$DEVICE"
sudo wipefs -n "$DEVICE"
```

For the **first installation only**, after verifying the empty disk, run `sudo mkfs.ext4 -L apex-state "$DEVICE"`. Make the mount persistent and check it before starting a worker.

```bash
UUID=$(sudo blkid -s UUID -o value "$DEVICE")
test -n "$UUID" || exit 1
sudo mkdir -p /var/lib/apex
if ! awk '$2 == "/var/lib/apex" { found=1 } END { exit !found }' /etc/fstab; then
  echo "UUID=$UUID /var/lib/apex ext4 defaults 0 2" | sudo tee -a /etc/fstab >/dev/null
fi
mountpoint -q /var/lib/apex || sudo mount /var/lib/apex
findmnt --target /var/lib/apex
test "$(findmnt -n -o UUID --target /var/lib/apex)" = "$UUID" || exit 1
sudo chown 10001:10001 /var/lib/apex
sudo chmod 0700 /var/lib/apex
read -rp 'Same verified 40-character Git commit: ' RELEASE
[[ "$RELEASE" =~ ^[a-f0-9]{40}$ ]] || exit 1
sudo mkdir -p /opt/apex-releases
CHECKOUT="/opt/apex-releases/$RELEASE"
sudo git clone https://github.com/Oscare96/Apex-game.git "$CHECKOUT"
sudo git -C "$CHECKOUT" checkout --detach "$RELEASE"
test "$(sudo git -C "$CHECKOUT" rev-parse HEAD)" = "$RELEASE" || exit 1
sudo docker build -f "$CHECKOUT/Dockerfile.show" -t "apex-worker:$RELEASE" "$CHECKOUT"
sudo bash "$CHECKOUT/deploy/container-acceptance.sh" "apex-worker:$RELEASE"
sudo docker image inspect "apex-worker:$RELEASE" --format '{{.Id}}'
```

The acceptance command runs with networking disabled. It checks the runtime UID, plays three fares, retries the same shift, verifies all clips and expects exactly three verified wins and zero external receipts. Stop if it fails.

## 4. Activate the offline pilot

Run on the VM. Use the actual dedicated project ID again. The supplied timer runs at 18:00 UTC daily. Change the unit's calendar before enabling if the owner selects a different showtime.

```bash
read -rp 'Dedicated APEX project ID: ' PROJECT_ID
sudo install -d -m 0750 /etc/apex
sudo ln -sfnT "$CHECKOUT" /opt/apex
sudo install -m 0644 "$CHECKOUT/deploy/shift.json" /etc/apex/shift.json
printf 'APEX_IMAGE=apex-worker:%s\nAPEX_PROJECT=%s\nAPEX_SECRET_VERSION=\n' "$RELEASE" "$PROJECT_ID" | sudo tee /etc/apex/worker.env >/dev/null
sudo install -m 0644 "$CHECKOUT"/deploy/apex-{shift.service,shift.timer,chat.service} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start apex-shift.service
sudo journalctl -u apex-shift.service -n 30 --no-pager
sudo cat /var/lib/apex/latest.json
sudo systemctl enable --now apex-shift.timer
systemctl list-timers apex-shift.timer
```

The first real shift uses its UTC date as the ID. Running the service twice that day resumes the same shift. Expect three manifests, one 720p recording and one 720×1280 highlight per fare. Enable external accounts only through the [channel acceptance procedure](CHANNELS.md).

## 5. Protect state, monitor and recover

From Cloud Shell, attach a daily snapshot schedule in the disk's region. Record the resource names. Snapshot access grants access to media, delivery sessions and the token cache. Restrict snapshot IAM accordingly.

```bash
gcloud compute resource-policies create snapshot-schedule apex-state-daily --region="$REGION" --daily-schedule --start-time=04:00 --max-retention-days=7 --on-source-disk-delete=keep-auto-snapshots --project="$PROJECT_ID"
gcloud compute disks add-resource-policies apex-state --resource-policies=apex-state-daily --zone="$ZONE" --project="$PROJECT_ID"
gcloud compute snapshots list --filter='sourceDisk~apex-state' --project="$PROJECT_ID"
```

Check `systemctl --failed`, `journalctl -u apex-shift -u apex-chat`, `df -h /var/lib/apex`, shift completion and provider receipts. Keep at least one inspected recording and the protected state snapshot before archiving old media. The worker stops starting fares below 256 MiB free. Logs and snapshot age need operator monitoring during the pilot. For an offline, application-consistent manual snapshot stop the timer, wait for an active shift to finish, stop chat, then snapshot the data disk and restart the enabled units. Schedule a restore drill before public streaming.

**Restore drill.** In Cloud Shell, choose an actual snapshot and a separate isolated recovery VM in the same zone. Create a new disk from it and attach as a secondary disk. Start with egress disabled in the app and the timer and chat stopped. Never attach a writable volume to two active workers.

```bash
read -rp 'Verified state snapshot: ' SNAPSHOT
read -rp 'Recovery VM name: ' RECOVERY_VM
gcloud compute disks create apex-state-restore --source-snapshot="$SNAPSHOT" --zone="$ZONE" --project="$PROJECT_ID"
gcloud compute instances attach-disk "$RECOVERY_VM" --disk=apex-state-restore --device-name=apex-state --zone="$ZONE" --project="$PROJECT_ID"
```

Mount the restored filesystem without formatting it. Install the same release, mount the restored state read-only for the initial test, and run the replay command in the [handoff](BUZZ_HANDOFF.md). Compare its policy digest, show count and receipts with the incident record. Reconcile provider-side receipts and any OAuth rotation since the snapshot before enabling outbound work.

**Rollback.** Stop the timer and chat, let an active shift finish or stop it deliberately and record the interruption. Point `/opt/apex` back to the previous accepted release and set `APEX_IMAGE` to its recorded tag. Reinstall its units and run `systemctl daemon-reload`. Run that image's offline acceptance and verify a copy of the retained state before resuming. Never roll live receipts backward without provider reconciliation.

**Cost stop.** Disable the timer and chat and stop the VM from Cloud Shell using `gcloud compute instances stop apex-worker --zone="$ZONE" --project="$PROJECT_ID"`. Persistent disks, snapshots, and NAT or network resources can still incur charges. Review the dedicated project's billing before removing retained resources. Buzz should report the commit, image ID, project, zone, timer, snapshot, verification output, spend estimate and any platform dashboard evidence. No live deployment occurred as part of the repository implementation.
