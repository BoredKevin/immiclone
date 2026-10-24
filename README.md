# Immiclone

A simple, lightweight tool to backup your Immich photos and videos across multiple cloud drives.

This tool manages a master Immich media library that's mounted to the cloud using rclone, and manages backup copies on other cloud drives (like another Google Drive account and Terabox).

Copying hundreds of gigabytes directly from a home server would hog all the home bandwidth and take days. Whilst paying for dedicated cloud sync servers or leaving VMs running 24/7 gets expensive fast.

Immiclone solves this by making  **your server** keep track of what needs copying, how much is done, and shows you a clean dashboard.

Whilst **free cloud runners** (like Google Cloud Console) replicates your files cloud-to-cloud, updates your dashboard in real-time, and vanishes when it's done.

---

### 1. Resume Anytime (Never Start Over)
If Google Cloud Shell closes or your laptop loses internet halfway through a 500 GB transfer, don't worry:
- The server saves your progress.
- Open a new terminal, paste the runner command again, and click **Resume**.
- It skips everything already copied and picks up right where it stopped.

### 2. Zero Passwords Left Behind
The worker machine doesn't keep your cloud passwords or rclone keys:
- It only loads your keys into temporary RAM memory while running.
- As soon as the transfer finishes or the terminal closes, everything is completely wiped clean.

### 3. Connects Privately (Even Behind Tailscale)
If your home server is hidden on a private Tailscale network:
- The dashboard automatically gives the worker a temporary key to reach your server.
- The worker talks to your server privately to get its marching orders, but transfers files directly between clouds on the public internet so speeds stay maxed out.

### 4. Smart Raw Copies (Skip Re-Encrypting)
If you're copying from one encrypted Google Drive to another:
- You don't need to decrypt the files and re-lock them.
- It copies the raw encrypted files directly. This saves CPU and ensures files match 100% byte-for-byte.

---

## Quickstart

### 1. Install on Your Server

Open a terminal on your Linux server where Immich is running:

```bash
git clone https://github.com/BoredKevin/immiclone.git /opt/immiclone
cd /opt/immiclone
sudo ./scripts/install.sh
```

This sets up the dashboard service and starts it on port `8080`.

### 2. Run a Copy Job

1. Open `http://your-server-ip:8080` in your browser.
2. Go to **Duplication Manager** ➔ click **+ New Transaction** to pick your source and destination folders.
3. Click **Copy Command**.
4. Open a free [Google Cloud Shell](https://shell.cloud.google.com/) (or any Linux machine/VPS) and paste the command:

```bash
curl -sSL http://your-server-ip:8080/worker.sh | bash -s -- --id worker-1234 --endpoint http://your-server-ip:8080 --token abc123xyz
```

5. The worker connects to your dashboard. Click **▶ Assign** on your job, and watch the transfer fly at gigabit speeds!

---

## Ready-Made Presets

When creating a job, you can pick from handy presets:
- **Raw Google Drive Mirror**: Fast server-side copy between two Google Drive accounts (no decryption needed).
- **Terabox Mirror**: Tuned settings that handle Terabox upload quirks safely without duplicates.
- **Custom**: Type in any source and destination remote you configured in Rclone.

---

## Dashboard Ports

| Port | What it is |
| :--- | :--- |
| `8080` | **Immiclone Dashboard** (Copy manager, worker status, settings, storage space) |
| `2283` | **Immich Web UI** (Your actual photo and video app) |
| `5572` | **Rclone GUI** (Live mount stats) |

---

## Running Tests

To verify that the code and APIs are working properly:

```bash
python tests/test_ui_and_services.py
```
