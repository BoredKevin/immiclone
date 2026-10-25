# Immiclone

A simple, lightweight tool to backup your Immich photos and videos across multiple cloud drives.

This tool manages a master Immich media library that's mounted to the cloud using rclone, and manages backup copies on other cloud drives (like another Google Drive account and Terabox).

Copying hundreds of gigabytes directly from a home server would hog all the home bandwidth and take days. Whilst paying for dedicated cloud sync servers or leaving VMs running 24/7 gets expensive fast.

Immiclone solves this by making  **your server** keep track of what needs copying, how much is done, and shows you a clean dashboard.

Whilst **cloud runners** replicates your files cloud-to-cloud, updates your dashboard in real-time, and vanishes when it's done.

> [!WARNING]
> ### USE STRICTLY AT YOUR OWN RISK — EXPERIMENTAL SOFTWARE
> 
> Immiclone is under rapid, breaking, active development. Things can, will, and frequently do break between commits. This is **not** a battle-tested, production-grade system yet, and you should **never** rely on this tool as your sole or primary backup method. Always maintain verified, independent offline copies of your irreplaceable media.
> 
> #### Legal Disclaimer & Limitation of Liability
> This software is provided on an **"AS IS"** and **"AS AVAILABLE"** basis, with all faults, defects, and errors, and without warranties of any kind—whether express, statutory, or implied (including, but not limited to, the implied warranties of merchantability, fitness for a particular purpose, non-infringement, or data integrity).
> 
> By downloading, cloning, deploying, running, or otherwise interacting with Immiclone (including the dashboard, API, worker scripts, or rclone integrations), you explicitly acknowledge and agree that:
> 1. **Full Assumption of Risk:** You voluntarily assume all risks related to testing and operating this software on your local host, network, cloud storage accounts, and remote compute instances.
> 2. **Comprehensive Release of Liability:** Under no circumstances shall **BoredKevin**, maintainers, or project contributors be liable for any direct, indirect, incidental, special, consequential, exemplary, or punitive damages whatsoever—including, without limitation, loss of data, unrecoverable data deletion, media corruption, cloud storage provider account suspensions or API bans, system downtime, bandwidth overages, or financial losses—arising out of or relating to your use or inability to use this software.
> 3. **Irrevocable Waiver:** You hereby **expressly, unconditionally, and irrevocably release, waive, and hold harmless** BoredKevin and all contributors from any and all legal claims, demands, suits, proceedings, liabilities, or expenses to the maximum extent permitted under applicable law.
 

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
curl -sSL https://raw.githubusercontent.com/BoredKevin/immiclone/refs/heads/main/worker/worker-stable.sh | bash -s -- --id worker-1234 --endpoint http://your-server-ip:8080 --token abc123xyz
```

5. The worker connects to your dashboard. Click **▶ Assign** on your job, and watch the transfer fly at gigabit speeds!

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
