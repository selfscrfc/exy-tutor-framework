# Local learning dashboard

Use the dashboard to connect multiple Exy learning workspaces, inspect their tasks and weekly plans, and record focus time. It reads the same instance registry and learning files as the CLI and MCP server. No copy of your learning history is stored in the browser.

## Start

From the shared framework repository:

```sh
.venv/bin/python scripts/dashboard.py
```

Open the printed address, normally `http://127.0.0.1:8765`. Leave the process running while using the dashboard. Stop it with Ctrl+C when finished; stopping the server does not pause a learner timer. Timers persist in the workspace and can be resumed or stopped after restarting the server.

Python and the existing runtime requirements are sufficient. The interface uses local HTML, CSS, and JavaScript without a frontend build, external fonts, or a hosted service. MCP dependencies are only needed to run the separate MCP server.

Optional arguments:

```sh
.venv/bin/python scripts/dashboard.py --registry ~/.config/exy-tutor/instances.json --port 8765
```

The server binds only to `127.0.0.1`. Use the exact printed address. The server checks the host, origin, and a per-launch request token for writes. This is a local personal tool, not a multi-user or remotely hosted service.

## Connect and switch workspaces

Choose **Connect workspace**, provide a short name such as `exy-ml`, and enter an initialized workspace folder such as `~/exy-ml`. Its `state/` directory is also accepted. The connection is added to the same registry used by your agents. The application checks the state before connecting and prevents duplicate paths or replacing an existing name with a different workspace.

Create a new empty workspace through the existing command before connecting it:

```sh
.venv/bin/python scripts/create_instance.py ../my-learning --objective "My learning objective"
```

Select a workspace in the sidebar to view its goals, current weekly plan, workload recommendation, and time totals. Changes from agents appear on the next refresh, normally every five seconds while the page is visible and dialogs are closed. Use the refresh button for an immediate update.

**Connection settings** lets you disconnect a workspace without deleting its files. Stop its running and paused timers first. Disconnecting also removes the name from the shared MCP registry. Agents will need the workspace reconnected to access it again. A broken connection does not prevent other workspaces from loading.

## Tasks and focus

- **This week** shows the outcomes in the latest plan revision covering today. **All outcomes** shows the full tree, with parent names and outcome groups identified.
- Search by title, ID, or notes, and filter by status.
- Open an outcome for its completion criteria, prerequisites, planned activities, permitted assistance, and recorded effort.
- Select **Focus** to prepare that outcome in the timer. Enter the activity and press **Start focus** when you actually begin.
- Optionally link an existing open learning session. The timer then updates that session's time ledger. With **Track time only**, it records focus without creating a learning session.
- Pause for interruptions, resume when ready, and use **Stop & save** to finish. The display includes saved intervals and the current interval. Daily and weekly totals include saved intervals only.

One timer may run per workspace. A reminder appears if a timer is running in another connected workspace; separate workspaces do not enforce a global timer limit. A timer started by an agent requires an explicit confirmation before the UI operates under its recorded owner identity. These labels coordinate trusted clients and are not authentication.

Timer requests retain the existing version checks, interval validation, persistent retry receipts, and four-hour confirmation guard. If a response is lost, the next timer action offers to retry the exact pending request. Reloading reads the committed state. Do not start a second operation merely because the first response was slow.

## What the overview means

Weekly and daily targets come from an agreed plan; the dashboard does not invent a schedule. Required workload estimates remain separate from the agreed commitment. Day boundaries follow the objective's time zone, or the known draft foundation time zone. If no time zone is known, daily totals remain unavailable.

Completed outcomes count only leaf goals with recorded completion evidence. Time is not converted into a mastery score. The dashboard does not mark goals complete, assess answers, edit the foundation, or write curricula. Continue those workflows with your tutor through the CLI or MCP. Manual time corrections remain available through those interfaces.

## Verification

The HTTP integration tests cover workspace connection and disconnection, state isolation, timer persistence and replay, stale versions, agent handoff, broken connections, and request boundaries. Run them with the rest of the suite:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Browser checks use isolated fixture workspaces, not a learner's real records. They cover task filters/details, session-linked start/pause/resume/stop, reloads, agent handoff, connection switching, native input validation, and narrow-screen layout.
