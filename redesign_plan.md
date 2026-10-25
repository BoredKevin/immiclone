To make Immiclone radically simpler, the layout overhaul needs to solve one core structural problem: **right now, the app splits a single continuous workflow across 4 tabs, 12 summary cards, and 5 separate lists/tables**.

Because of this fragmentation, the same data is repeated in multiple places (for example, Local SSD free space and the 10 GB VFS cache appear on both `Storage Matrix` and `Media & Cache`), while permanent setup tools (like the `Compute Worker Launcher` bash script) take up massive amounts of vertical space even when you aren't using them.

Here is a complete layout overhaul plan to condense the entire app into a **Single-Screen Pipeline Layout** with zero wasted space.

---

## 1. The New Layout Blueprint (Before vs. After)

Instead of making the user click through 4 tabs to piece together what the system is doing, the entire app can be unified into **two vertical zones** on a single screen:

1. **Top Zone (The 3-Stage Pipeline Header):** Replaces the 4 navigation tabs AND the 12 summary cards across all tabs. It shows the entire system flow from left to right and acts as the navigation selector.

2. **Bottom Zone (The Contextual Workspace):** Changes dynamically based on which stage of the pipeline you click (Stage 1: Local Library, Stage 2: Cloud Sync, or Stage 3: Cloud Backup).

```text
+-----------------------------------------------------------------------------------+
| [Logo] Immiclone                     [● Tailscale] [⚙ Settings] [Immich ↗]        |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  STAGE 1: LOCAL SSD & CACHE  ===[ 1.8 MB/s ↑ ]===>  STAGE 2: MAIN CLOUD (bkc:)   |
|  +-------------------------+                        +--------------------------+  |
|  | 💾 701 MB Free (92% SSD)|                        | 137.9 GB Used (of 5.0 TB)|  |
|  | 10/10 GB Cache (1,525)  |                        | 4,618 Total Media Files  |  |
|  | [Manage Local Files]    |                        | ⚡ 2 Uploading | 10 Failed|  |
|  +-------------------------+                        +--------------------------+  |
|                                                                  ||               |
|                                                                  \/               |
|                                                     STAGE 3: OFFSITE BACKUP       |
|                                                     +--------------------------+  |
|                                                     | bkc: ➔ 1337quota:crypt   |  |
|                                                     | ⏳ Waiting for Worker    |  |
|                                                     | [🚀 Start Backup Worker] |  |
|                                                     +--------------------------+  |
+-----------------------------------------------------------------------------------+
|  ACTIVE WORKSPACE (Shows files/jobs for the selected stage below)                 |
|  [ ⚡ Uploading Now (2) ] [ ⚠️ Failed (10) ] [ 💾 On SSD (1,525) ] [ ☁️ Cloud (3,093) ] |
|  -------------------------------------------------------------------------------  |
|  🎬 copy_F2F9C7F6.mov       [=================>  ] 97%      1.6 MB/s    Uploading |
|  🖼️ 8fac5481-e768.jpg       [====================] 100%     Verifying   Finalizing|
|  🖼️ IMG_7888.jpg            ✅ Cached on SSD + Cloud         4.7 MB      Oct 25    |
+-----------------------------------------------------------------------------------+
```

---

## 2. Four-Phase Consolidation Plan

### Phase 1: Eliminate the `Storage Matrix` Tab (Merge 12 Cards into 3 Pipeline Cards)

Currently, you have 4 cards in `Storage Matrix`, 4 cards in `Media & Cache`, and 4 cards in `Local Rclone Mount`. Many of them show identical or overlapping data.

* **Delete `Storage Matrix` as a standalone tab**.
* **Hide `VOLATILE RAM-DISK (/DEV/SHM)` automatically** when its capacity is `0 GB`. Only render it if a user actually mounts a RAM disk.
* **Combine `LOCAL ROOT SSD` and `RCLONE VFS DISK CACHE` into Stage 1 ("Local Server Storage")**: Show one dual-layer bar (or two compact stacked bars inside a single card) so the user immediately sees how their 10 GB cache relates to their 28.8 GB root SSD.
* **Combine `AUTHORITATIVE CLOUD (BKC:)`, `TOTAL LIBRARY MEDIA`, and `CURRENT UPLOAD SPEED` into Stage 2 ("Main Cloud Drive")**: Display the 137.9 GB / 5.0 TB cloud capacity alongside the live upload speed (`1.8 MB/s`) and total indexed photo count (`4,618`).

### Phase 2: Merge `Media & Cache` and `Local Rclone Mount` into One Unified File Table

Right now, `Local Rclone Mount` shows files currently uploading, while `Media & Cache` shows files that have finished uploading or are sitting in the local cache. Splitting them into two tabs hides active uploads when browsing media, and hides the media library when checking uploads.

* **Merge both tables into a single "Library & Sync Activity" table**.
* **Pin active uploads to the top of the table:** Whenever files are actively transferring (`Active 2`), keep them pinned at the top of the list with their live progress bars and a `[Pause Uploads]` button right in the table header.
* **Unify the filter pills above the search bar:** Replace the separate filter bars on both tabs with one unified lifecycle filter bar:
  * `All Media (4,618)`
  * `⚡ Uploading (2)`
  * `⚠️ Failed Uploads (10)` *(with a 1-click "Retry All" action)*
  * `💾 Cached on Local SSD (1,525)`
  * `☁️ Stored in Cloud Only (3,093)`

### Phase 3: Collapse `Duplication Manager` from 3 Stacked Sections into 1 Card List + 1 Modal

`Duplication Manager` is visually overwhelming because it displays the `Compute Worker Launcher` (with sub-tabs and a horizontal-scrolling bash script), the `Duplication Transactions` list (with 5 filter pills), and the `Compute Workers Pool` (with 3 filter pills) all at the same time.

* **Remove the permanent `Compute Worker Launcher` box from the page**. Put it inside a clean pop-up modal or slide-out drawer that only opens when the user clicks **`[🚀 Start Worker]`**.
* **Merge the `Compute Workers Pool` directly into the Backup Job Card**. Instead of making the user scroll down to a separate `Compute Workers Pool` section to see why their backup isn't running, display the worker status right inside the transaction card's header:
  * If no worker is online: Show a yellow pill `⚠️ No Worker Online` next to a prominent **`[Launch Free Cloud Worker]`** button.
  * If a worker is connected: Show a green pill `🟢 Connected: worker-9480 (Google Cloud Shell)` right on the job card.
* **Remove the 8 filter pills (`All (1)`, `Running (0)`, `Queued (0)`, etc.)**. Unless a user has dozens of concurrent backup transactions, a simple list sorted by active jobs first (with a single `[Clear Finished]` button) is much cleaner.
* **Hide raw CLI flags (`--size-only --transfers=4...`) behind an `ℹ️` tooltip or the `Edit` modal**.

### Phase 4: Clean Up the Top Header Bar

The top header currently has 5 interactive pills/buttons competing for attention (`Poll: 500ms`, `Tailscale: Connected`, `Settings`, `Immich Server ↗`, `Rclone GUI ↗`).

* **Move `Poll: 500ms` inside the `Settings` modal**. Almost no user changes UI polling frequency after initial setup.
* **Simplify `Tailscale: Connected` to a compact status indicator** (`🟢 Tailscale`) that opens the Tailscale config modal when clicked.
* **Group `Immich Server ↗` and `Rclone GUI ↗`** as secondary ghost links on the far right, keeping `[⚙ Settings]` as the primary utility button.

---

## 3. Summary of Visual Noise Reduction

By executing this layout overhaul, here is how much visual complexity disappears immediately:

| UI Element | Current Design | Overhauled Layout |
| --- | --- | --- |
| **Top-Level Navigation Tabs** | 4 separate tabs | **0 tabs** (3 interactive Pipeline Cards act as navigation) |
| **Top Metric / Summary Cards** | 12 cards spread across 3 tabs | **3 unified Pipeline Cards** |
| **File & Transfer Tables** | 2 separate tables on different tabs | **1 unified table** with lifecycle filter pills |
| **Duplication Page Sections** | 3 full-width sections + 8 filter pills | **1 Backup Job list** + **1 on-demand Worker Modal** |
| **Unused / Redundant Widgets** | `0 GB RAM-Disk`, duplicated SSD & Cache bars, raw cURL bar | **Hidden until needed** or merged |

---

## 4. Recommended Implementation Order

If you are refactoring your frontend code, tackle the changes in this order for the fastest visual payoff with minimal state rewrites:

1. **Step 1 (Quickest Cleanup):** Move the `Poll: 500ms` selector into Settings, hide the `0 GB Volatile RAM-Disk` card when total size is `0`, hide the raw Rclone CLI flags on backup cards, and remove the `0`-count filter pills on `Duplication Manager`.
2. **Step 2 (Modal Extraction):** Move the `Compute Worker Launcher` and `Compute Workers Pool` out of the main flow and into a guided **"Launch / Manage Workers" Modal** triggered directly from the Backup Job card.
3. **Step 3 (Table Unification):** Merge the `Local Rclone Mount` upload queue rows into the top of the `Media & Cache` table and add the unified status filter pills (`Uploading`, `Failed`, `Cached on SSD`, `Cloud-Only`).
4. **Step 4 (The Pipeline Header):** Replace the top tab bar and `Storage Matrix` with the 3-Stage Pipeline Header cards (`Local SSD & Cache` ➔ `Main Cloud` ➔ `Offsite Backup`).
