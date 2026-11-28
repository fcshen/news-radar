#!/usr/bin/env bash
# 把 data/ 提交并推到远端 main。
#
# 为什么不用 git pull ---------------------------------------------------------
# runner 里的分支不一定配了 upstream，git pull 会立刻以
#   "There is no tracking information for the current branch"
# 失败。而这个错误在 workflow 里被 `|| true` 吞掉，紧接着 git push 因
# non-fast-forward 被拒、又被 `|| echo` 吞掉——两处都显示 success，
# 实际一条数据都没上去。
#
# 2026-11-28 21:07 就是这样静默停摆的：主循环在跑、进程活着、Actions 显示
# 绿色，手机看板却冻在 21:05。所以这里改成显式 fetch + rebase，不碰 upstream。
#
# 为什么失败要写标记文件 ------------------------------------------------------
# 光在日志里 echo 没用，没人会天天翻日志。失败就写一个标记，由 workflow 末尾
# 的步骤读它：有标记就推手机 + 让整个 run 变红。红的 run 我这边查 API 就能
# 发现，不用等用户来问。
set -u

MSG="${1:-data: $(date -u +%Y-%m-%dT%H:%MZ)}"
FLAG="${RUNNER_TEMP:-/tmp}/pushfail.log"

git add data/ 2>/dev/null || true
if git diff --cached --quiet; then
  echo "· 无变更"
else
  git commit -q -m "$MSG" || true
  echo "· 已提交：$MSG"
fi

ok=0
for i in 1 2 3; do
  git fetch -q origin main 2>/dev/null || true
  # 上一轮残留的 rebase 会让之后每一次都失败（"rebase in progress"），
  # 先无条件清掉——这是最容易被忽略的慢性死锁。
  git rebase --abort 2>/dev/null || true

  if ! git rebase -q origin/main 2>/tmp/rb.err; then
    echo "! rebase 冲突，改以远端为基准重来"
    sed -n '1,5p' /tmp/rb.err
    git rebase --abort 2>/dev/null || true
    # data/ 全是可再生成的文件，丢掉本地这次提交远好过卡死；
    # 未推送的事件会在下一轮回溯窗口里重新抓到。
    git reset -q --hard origin/main
    echo "! 已回到 origin/main"
    sleep 3
    continue
  fi

  if git push -q origin HEAD:main 2>/tmp/ps.err; then
    echo "✓ 已推送"
    ok=1
    break
  fi
  echo "! 第 $i 次推送失败："
  sed -n '1,5p' /tmp/ps.err
  sleep 5
done

if [ "$ok" = "1" ]; then
  rm -f "$FLAG"
  exit 0
fi

echo "$(date -u +%FT%TZ) 推送失败" >> "$FLAG"
exit 1
