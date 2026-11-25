"""Claude Code 세션 transcript(JSONL)에서 사용자 프롬프트를 추출해 마크다운 표로 저장합니다.

사용법: python chat_history.py <출력 파일> [세션 ID]
"""
import glob
import json
import os
import re
import sys
from datetime import datetime

SKIP_PREFIXES = ("<task-notification", "<local-command-")


def find_transcript(session_id):
    base = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "projects")
    if session_id and re.fullmatch(r"[0-9a-fA-F-]{36}", session_id):
        hits = glob.glob(os.path.join(base, "*", session_id + ".jsonl"))
        if hits:
            return hits[0]
    # 세션 ID를 알 수 없으면 가장 최근에 기록된 transcript(현재 세션)를 사용합니다.
    files = glob.glob(os.path.join(base, "*", "*.jsonl"))
    if not files:
        sys.exit("transcript 파일을 찾을 수 없습니다: " + base)
    return max(files, key=os.path.getmtime)


def prompt_text(entry):
    """사용자가 직접 입력한 프롬프트이면 텍스트를, 아니면 None을 반환합니다."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isCompactSummary") or entry.get("isSidechain"):
        return None
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        text = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    elif isinstance(content, str):
        text = content
    else:
        return None
    text = text.strip()
    if not text or text.startswith(SKIP_PREFIXES):
        return None
    cmd = re.search(r"<command-name>(.*?)</command-name>", text, re.S)
    if cmd:
        args = re.search(r"<command-args>(.*?)</command-args>", text, re.S)
        text = (cmd.group(1).strip() + " " + (args.group(1).strip() if args else "")).strip()
    return text


def local_time(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def cell(text):
    return text.replace("\r\n", "\n").replace("|", "\\|").replace("\n", "<br>")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        sys.exit("사용법: python chat_history.py <출력 파일> [세션 ID]")
    out_path = sys.argv[1]
    path = find_transcript(sys.argv[2] if len(sys.argv) > 2 else "")

    rows = []  # [시각, 내용, input, output, 집계된 message.id 집합]
    for line in open(path, encoding="utf-8"):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        text = prompt_text(entry)
        if text is not None:
            rows.append([local_time(entry["timestamp"]), text, 0, 0, set()])
            continue
        if entry.get("type") == "assistant" and rows and not entry.get("isSidechain"):
            msg = entry.get("message") or {}
            usage = msg.get("usage")
            # 응답 블록마다 같은 message.id와 usage가 반복 기록되므로 한 번만 합산합니다.
            if usage and msg.get("id") not in rows[-1][4]:
                rows[-1][4].add(msg.get("id"))
                rows[-1][2] += (usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
                                + usage.get("cache_read_input_tokens", 0))
                rows[-1][3] += usage.get("output_tokens", 0)

    session = os.path.splitext(os.path.basename(path))[0]
    lines = [
        "# 채팅 기록",
        "",
        f"- 세션 ID: `{session}`",
        f"- 작성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 프롬프트 수: {len(rows)}",
        "- 토큰: Input = input + cache 생성 + cache 읽기, Output = output (서브에이전트 사용량 제외)",
        "",
        "| No | 입력 시각 | 사용자 입력 내용 | Input 토큰 | Output 토큰 |",
        "|---:|---|---|---:|---:|",
    ]
    for i, (ts, text, tin, tout, _) in enumerate(rows, 1):
        lines.append(f"| {i} | {ts} | {cell(text)} | {tin:,} | {tout:,} |")
    total_in = sum(r[2] for r in rows)
    total_out = sum(r[3] for r in rows)
    lines.append(f"| | **합계** | | **{total_in:,}** | **{total_out:,}** |")

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{out_path}: 프롬프트 {len(rows)}개, Input {total_in:,} / Output {total_out:,} (transcript: {path})")


if __name__ == "__main__":
    main()
