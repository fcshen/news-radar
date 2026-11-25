#!/usr/bin/env bash
# 改完代码后一键提交并推送（本地开发用，云端 Actions 不会执行它）
#
#   bash tools/push.sh "提交说明"
#
# 设计要点
# 1. data/ 由云端 Actions 每 30 分钟写入，本地那份只是运行时副本，
#    绝不能反向覆盖云端，所以提交时一律排除 data/。
# 2. 先提交、再 rebase、最后推送：rebase 要求工作区干净，顺序反过来会卡住。
# 3. 本地 data/ 的改动会阻塞 rebase，先备份到 data_local_backup/ 再从远端版本重置。
# 4. 只提交“已跟踪文件”的改动（git add -u），新增文件需显式 git add，避免误加临时文件。

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

MSG="${1:-chore: 同步本地改动}"

echo "== 1/5 备份本地运行时数据"
if [ -n "$(git status --porcelain -- data 2>/dev/null)" ]; then
  mkdir -p data_local_backup
  cp -f data/*.json data_local_backup/ 2>/dev/null
  echo "   已备份到 data_local_backup/"
  git checkout -- data 2>/dev/null
fi

echo "== 2/5 暂存改动（排除 data/）"
git add -u -- . ':!data'

if git diff --cached --quiet; then
  echo "   没有需要提交的改动"
  exit 0
fi
git --no-pager diff --cached --stat

echo "== 3/5 提交"
git -c user.name="fcshen" -c user.email="fcshen@users.noreply.github.com" \
    commit -q -m "$MSG" || exit 1

echo "== 4/5 同步远端"
git fetch -q origin main || { echo "   拉取失败，检查网络"; exit 1; }
if ! git rebase -q origin/main; then
  echo "   自动 rebase 失败，请手动处理：git rebase origin/main"
  exit 1
fi

echo "== 5/5 推送"
git push -q origin main || { echo "   推送失败"; exit 1; }
echo "完成: $(git log --oneline -1)"
