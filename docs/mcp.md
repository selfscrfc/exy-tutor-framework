# MCP integration

The local stdio server exposes the shared learning workflow to trusted MCP clients. It uses the official Python MCP SDK, pinned in `requirements-mcp.txt`. It does not expose a network listener or accept arbitrary filesystem paths from tool calls.

## Install and register instances

```sh
.venv/bin/python -m pip install -r requirements-mcp.txt
```

Run `init` on existing instances once to add the new logs. Create a local registry outside the published repository, for example `~/.config/exy-tutor/instances.json`:

```json
{
  "schema_version": 1,
  "instances": {
    "exy-ml": "/absolute/path/to/exy-ml/state"
  }
}
```

Only registered names are accepted. An operator edits this file to add another instance; agents cannot add arbitrary roots through MCP tools. Give agents collaborating on one goal the same instance name. Each instance has its own timer and learning history.

For Codex, register the executable using absolute paths:

```sh
codex mcp add exy-tutor -- /absolute/path/to/exy-tutor-framework/.venv/bin/python /absolute/path/to/exy-tutor-framework/scripts/mcp_server.py --registry /absolute/path/to/instances.json
```

For another stdio MCP client, use its equivalent server configuration:

```json
{
  "mcpServers": {
    "exy-tutor": {
      "command": "/absolute/path/to/exy-tutor-framework/.venv/bin/python",
      "args": [
        "/absolute/path/to/exy-tutor-framework/scripts/mcp_server.py",
        "--registry",
        "/absolute/path/to/instances.json"
      ]
    }
  }
}
```

Use the client's reconnect/reload mechanism after registration. The framework does not restart other agents automatically.

## Tools

| Tool | Purpose |
| --- | --- |
| `list_instances` | Discover registered instance names |
| `get_context` | Read the foundation, goals, latest plans/session, recent assessments, timers, workload, and state revision |
| `get_input_template` | Get a blank supported input record |
| `analyze_workload` | Save an evidence-labelled effort/deadline/capacity analysis without changing commitments |
| `get_pace` | Read daily time, schedule adherence, effort samples, and a provisional projection |
| `manage_timer` | Start, pause, resume, or stop a learner-focus timer |
| `record_time` | Add an actual interval or append a correction |
| `tutor_action` | Use the same goal, plan, session, assessment, card, and weekly-report operations as the CLI |

For `tutor_action`, `data` contains the template record for foundation, goal, plan, or card writes. `configure` takes an objective patch. The other payloads are:

| Action | Data fields |
| --- | --- |
| `assessment_add` | `assessment`, optional `session_id`, optional `complete` |
| `session_start` | `week`, optional `goal_ids` |
| `session_checkpoint`, `session_end` | `note`, optional `session_id`, optional manual `minutes` |
| `review_next`, `review_skip` | Optional `session_id` |
| `review_answer` | `response`, optional `session_id` |
| `review_rate` | `rating`, `seconds`, optional `session_id` |
| `week_close` | `week`, optional `notes` |

The local dashboard in `~/exy-dashboard` uses this same registry and state. Connecting or disconnecting a workspace in the UI also changes which names MCP clients can access.

## Coordination between agents

1. Call `list_instances`, then `get_context` for the intended instance.
2. Read the current state before deciding to change it. Workload analyses and `tutor_action` writes require the returned `state_revision`.
3. Give each logical write a stable `request_id`. Retry the same request with the same ID and arguments after transport failures. A different payload with that ID is rejected.
4. After a revision conflict, refresh context and reconsider the proposed change. Do not silently overwrite another agent's work.
5. Timer transitions use their owner label and `expected_version`. A second running timer is rejected. Actor labels are traceability, not an authorization boundary between mutually hostile clients.
6. Start a timer only for actual learner activity. Pauses exclude interrupted time; agent computation does not count as study. Long unattended intervals require explicit confirmation or correction.

All tools use the existing file lock, staged validation, and recovery journal. MCP receipts are stored in the instance, so retries remain safe across server restarts. Replayed requests return the original operation result and the current state revision. The generic tutor write tool changes only the selected instance and cannot run shell commands.

The protocol test launches the real stdio entrypoint and checks discovery, structured results, allowlisting, optimistic concurrency, retries, timer ownership, manual time, and workload calculations. It does not establish compatibility with every third-party client; clients must support stdio MCP.

References: [official Python SDK](https://github.com/modelcontextprotocol/python-sdk), [MCP server guide](https://modelcontextprotocol.io/docs/develop/build-server).
