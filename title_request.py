"""Request a title through Claude's tool-free control operation, never a chat turn."""
import argparse, json, os, queue, subprocess, sys, tempfile, threading, time

TIMEOUT = 20
MAX_INPUT = 2000
MAX_TITLE = 80


def fallback(description):
    return " ".join(description.split()[:8])[:MAX_TITLE].strip() or "New chat"


def exchange(process, messages, request, deadline):
    request_id = request["subtype"]
    process.stdin.write(json.dumps({"type": "control_request", "request_id": request_id,
                                    "request": request}) + "\n")
    process.stdin.flush()
    while True:
        packet = messages.get(timeout=max(0, deadline - time.monotonic()))
        if packet is None:
            raise ValueError("Title process ended")
        if packet.get("type") == "control_request":
            raise ValueError("Unexpected interactive request")
        response = packet.get("response", {})
        if packet.get("type") != "control_response":
            continue
        if not isinstance(response, dict):
            raise ValueError("Invalid control response")
        if response.get("request_id") != request_id:
            continue
        if response.get("subtype") != "success":
            raise ValueError("Title operation unavailable")
        result = response.get("response", {})
        if not isinstance(result, dict):
            raise ValueError("Invalid title response")
        return result


def generate(description, binary="claude", model="haiku"):
    if model == "haiku":
        model = "claude-haiku-5-5"
    description = description[:MAX_INPUT]
    local_title = fallback(description)
    if not description.strip():
        return local_title
    process = None
    reader = None
    temporary = None
    try:
        temporary = tempfile.TemporaryDirectory(prefix="olympus-title-", ignore_cleanup_errors=True)
        if temporary is not None:
            folder = temporary.name
            environment = {**os.environ, "CLAUDE_CODE_DISABLE_THINKING": "1",
                           "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                           "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1",
                           "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "200",
                           "ANTHROPIC_SMALL_FAST_MODEL": model}
            process = subprocess.Popen(
                [binary, "-p", "--input-format", "stream-json", "--output-format", "stream-json",
                 "--verbose", "--model", model, "--tools", "", "--safe-mode", "--setting-sources", "",
                 "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence",
                 "--system-prompt", "Serve title control requests only.", "--permission-mode", "dontAsk",
                 "--settings", '{"disableAllHooks":true,"alwaysThinkingEnabled":false}',
                 "--max-budget-usd", "0.01"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace", cwd=folder, env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            messages = queue.Queue(maxsize=64)

            def read_messages():
                try:
                    for unused in range(64):
                        line = process.stdout.readline()
                        if not line or len(line) > 2_000_000:
                            break
                        packet = json.loads(line)
                        if isinstance(packet, dict):
                            messages.put_nowait(packet)
                except (ValueError, OSError, queue.Full):
                    pass
                finally:
                    try:
                        messages.put_nowait(None)
                    except queue.Full:
                        pass

            reader = threading.Thread(target=read_messages, daemon=True)
            reader.start()
            deadline = time.monotonic() + TIMEOUT
            exchange(process, messages, {"subtype": "initialize", "hooks": {}}, deadline)
            response = exchange(process, messages, {"subtype": "generate_session_title",
                                "description": description, "persist": False}, deadline)
            title = response.get("title")
            if not isinstance(title, str) or not title.strip() or len(title) > MAX_TITLE:
                return local_title
            if any(ord(character) < 32 for character in title):
                return local_title
            return title.strip()
    except (OSError, ValueError, TypeError, queue.Empty, subprocess.SubprocessError):
        return local_title
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=2)
            except (OSError, subprocess.SubprocessError):
                pass
            try:
                process.stdin.close()
            except OSError:
                pass
            if reader is not None:
                reader.join(timeout=1)
            try:
                process.stdout.close()
            except OSError:
                pass
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", default="claude")
    parser.add_argument("--model", default="claude-haiku-5-5")
    arguments = parser.parse_args()
    print(json.dumps({"title": generate(sys.stdin.read(MAX_INPUT), arguments.cli, arguments.model)}))
