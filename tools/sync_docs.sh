#!/usr/bin/env bash
# 把本机归档目录里的文档同步到仓库 docs/，然后提示你提交。
#
#   bash tools/sync_docs.sh                 # 默认从 ../news-radar-归档 取
#   bash tools/sync_docs.sh "D:/某处/归档"   # 指定源目录
#
# 背景：文档主副本放在仓库外的 D:\news-radar-归档（含旧备份 zip），
# 仓库 docs/ 只是镜像，方便在 GitHub 上读。改完主副本跑一次这个脚本即可，
# 免得两处内容慢慢走偏。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-$(dirname "$ROOT")/news-radar-归档}"

FILES=("工作文档.md" "运维手册.md" "新会话提示词.md")

if [ ! -d "$SRC" ]; then
  echo "找不到源目录：$SRC" >&2
  echo "用法：bash tools/sync_docs.sh <归档目录>" >&2
  exit 1
fi

mkdir -p "$ROOT/docs"
changed=0
for f in "${FILES[@]}"; do
  if [ ! -f "$SRC/$f" ]; then
    echo "跳过（源目录里没有）：$f" >&2
    continue
  fi
  if cmp -s "$SRC/$f" "$ROOT/docs/$f"; then
    echo "无变化：$f"
  else
    cp "$SRC/$f" "$ROOT/docs/$f"
    echo "已更新：$f"
    changed=1
  fi
done

if [ "$changed" -eq 0 ]; then
  echo "docs/ 已是最新，无需提交。"
  exit 0
fi

echo
echo "下一步："
echo "  cd \"$ROOT\""
echo "  export https_proxy=http://127.0.0.1:7897 http_proxy=http://127.0.0.1:7897"
echo "  bash tools/push.sh \"docs: 同步归档文档\""
