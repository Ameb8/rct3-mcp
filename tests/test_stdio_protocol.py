"""End-to-end integration test for stdio MCP protocol transport and stdout isolation."""

import json
import subprocess
import sys


def test_stdio_protocol_and_stdout_isolation():
    # Launch rct3-mcp subprocess
    proc = subprocess.Popen(
        [sys.executable, "-m", "rct3_control.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        assert proc.stdin is not None
        assert proc.stdout is not None

        # 1. Send initialize request
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-runner", "version": "1.0.0"},
            },
        }
        proc.stdin.write(json.dumps(init_req) + "\n")
        proc.stdin.flush()

        raw_resp = proc.stdout.readline()
        assert raw_resp.strip(), "Expected response on stdout"
        # Must be pure JSON
        init_resp = json.loads(raw_resp)
        assert init_resp["jsonrpc"] == "2.0"
        assert init_resp["id"] == 1
        assert "serverInfo" in init_resp["result"]
        assert init_resp["result"]["serverInfo"]["name"] == "rct3-control"

        # 2. Send initialized notification
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        # 3. Call tools/list
        proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n"
        )
        proc.stdin.flush()

        raw_tools = proc.stdout.readline()
        tools_resp = json.loads(raw_tools)
        assert tools_resp["id"] == 2
        tool_names = {t["name"] for t in tools_resp["result"]["tools"]}
        assert "status" in tool_names
        assert "observe" in tool_names
        assert "click" in tool_names
        assert "stop" in tool_names

        # 4. Call status tool
        proc.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "status", "arguments": {}},
                }
            )
            + "\n"
        )
        proc.stdin.flush()

        raw_status = proc.stdout.readline()
        status_resp = json.loads(raw_status)
        assert status_resp["id"] == 3
        assert "content" in status_resp["result"]

        # 5. Call observe tool
        proc.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "observe", "arguments": {}},
                }
            )
            + "\n"
        )
        proc.stdin.flush()

        raw_obs = proc.stdout.readline()
        obs_resp = json.loads(raw_obs)
        assert obs_resp["id"] == 4
        content = obs_resp["result"]["content"]
        # Verify ImageContent returned
        img_items = [c for c in content if c.get("type") == "image"]
        assert len(img_items) == 1
        assert img_items[0]["mimeType"] == "image/png"

    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=2)
        assert proc.stderr is not None
        stderr_output = proc.stderr.read()
        # Verify ordinary server logs went to stderr, not stdout
        assert "Starting RCT3 MCP server on stdio" in stderr_output
