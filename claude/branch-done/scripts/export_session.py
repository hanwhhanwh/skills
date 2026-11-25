"""Claude Code 세션 transcript(JSONL)를 /export와 비슷한 텍스트 대화록으로 저장합니다.

사용법: python export_session.py <출력 파일> [세션 ID]
마지막 줄에 사용한 transcript 경로를 출력합니다.
"""
import json
import os
import sys

# transcript 탐색과 프롬프트 판별은 같은 폴더의 chat_history.py(chat-history 스킬 사본)를 씁니다.
from chat_history import find_transcript, prompt_text

MAX_RESULT_LINES = 10


def indent(text, first, rest):
    lines = text.rstrip().splitlines() or [""]
    return "\n".join([first + lines[0]] + [rest + l for l in lines[1:]])


def tool_call(block):
    args = block.get("input") or {}
    summary = next((str(v) for v in args.values() if isinstance(v, str)), "")
    summary = summary.splitlines()[0] if summary else ""
    return f"● {block.get('name')}({summary[:120]})"


def tool_result(block):
    content = block.get("content")
    if isinstance(content, list):
        content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    lines = (content or "").strip().splitlines() or ["(출력 없음)"]
    if len(lines) > MAX_RESULT_LINES:
        lines = lines[:MAX_RESULT_LINES] + [f"… +{len(lines) - MAX_RESULT_LINES} lines"]
    return indent("\n".join(lines), "  ⎿  ", "     ")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        sys.exit("사용법: python export_session.py <출력 파일> [세션 ID]")
    out_path = sys.argv[1]
    if not os.path.splitext(out_path)[1]:
        out_path += ".txt"  # /export와 같이 확장자가 없으면 .txt를 붙입니다.
    path = find_transcript(sys.argv[2] if len(sys.argv) > 2 else "")

    parts = []
    for line in open(path, encoding="utf-8"):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("isSidechain"):
            continue
        text = prompt_text(entry)
        if text is not None:
            parts.append(indent(text, "> ", "  "))
            continue
        content = (entry.get("message") or {}).get("content")
        if entry.get("type") not in ("user", "assistant") or not isinstance(content, list):
            continue
        for block in content:
            kind = block.get("type") if isinstance(block, dict) else None
            if entry["type"] == "assistant" and kind == "text" and block.get("text", "").strip():
                parts.append(indent(block["text"], "● ", "  "))
            elif entry["type"] == "assistant" and kind == "tool_use":
                parts.append(tool_call(block))
            elif entry["type"] == "user" and kind == "tool_result":
                parts.append(tool_result(block))

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n\n".join(parts) + "\n")
    print(f"{out_path}: 항목 {len(parts)}개")
    print(path)


if __name__ == "__main__":
    main()
