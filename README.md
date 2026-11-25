# 金融事件雷达

7×24 盯住国内外一手信息，去重聚类后按重要性分级推送。面向 A 股、ETF、期货，零成本运行。

---

## 三步开始用

### 1. 电脑：双击桌面的「金融事件雷达」

桌面上放了一个入口 `金融事件雷达.bat`，双击即用。它只是跳转到本目录再调用 `start.bat`，
所以**即使本文件夹改名或搬位置，只要改桌面那个文件里的路径即可**，程序本身不用动。

也可以直接双击本目录里的 `start.bat`。

会弹一个黑窗口，自动做三件事：装依赖（只第一次）、起网页、打开浏览器。
**这个窗口要一直开着**，关了采集就停。

窗口里会显示两个地址：

```
电脑打开：  http://127.0.0.1:8000/
手机打开：  http://172.20.10.3:8000/
```

下面的二维码可以用手机直接扫。

> 如果没装 Python：去 https://www.python.org/downloads/ 装 3.10 或更高，
> **安装时务必勾选 “Add Python to PATH”**，然后重新双击。

### 2. 手机：装成 App

手机和电脑连同一个 WiFi，用浏览器打开上面那个「手机打开」的地址，然后：

- **iPhone**：Safari → 分享 → 添加到主屏幕
- **安卓**：浏览器菜单 → 添加到主屏幕 / 安装应用

桌面会多一个雷达图标，点开是全屏的，没有地址栏，和 App 一样。

> 打不开的话，多半是 Windows 防火墙拦了。第一次运行时会弹窗问是否允许，
> 要选「允许访问」。没弹窗就去 控制面板 → Windows Defender 防火墙 → 允许应用通过防火墙，
> 把 Python 的「专用」勾上。

### 3. 手机：开通推送

1. App Store 搜 **Bark**（免费）装上，打开，复制它给你的那条地址
2. 浏览器打开 `http://电脑IP:8000/setup`
3. 粘进去 → 保存 → 点「发一条测试」

手机响了就成了。之后 L2 以上事件会自动推给你，不用开着网页。

---

## 看板怎么用

- **推荐**：只看 L1 以上，日常就看这个
- **强提醒 / 即时 / 摘要**：按级别筛
- **全部**：连 L0 归档也显示，复盘用
- **国内 / 海外**：同一套流，只是按来源地区筛
- 每条卡片**点一下就展开**全文；右侧「原文 ↗」跳到出处
- 每条都带来源名和等级徽章（官方 / 交易所 / 权威媒体 / 媒体）
- 「影响（推断）」单独一行，和事实分开——事实是搬运的，推断是模型给的

数据每 20 秒自动刷新，切到后台会停，回来立刻刷。

---

## 关于成本

本机运行完全免费，不注册任何账号。手机推送用 Bark，也免费。
只有想做到「电脑关机也 7×24」时，才需要 GitHub Actions（免费额度够）或一台云服务器（约 50–150 元/年）。

---

## 一、命令行用法（排查问题用）

```bash
pip install -r requirements.txt
python main.py --once --dry-run      # 跑一轮，只打印不推送
python tools/health.py               # 体检所有渠道，看谁挂了
python tools/compare.py              # 用历史数据对照新旧打分
python app.py --no-browser           # 只起服务，不开浏览器
```

> 本机跑时，路透、FT、NYT、SCMP、半岛等海外源大概率超时（国内网络不可达），
> 这是正常的——它们由云端补。国内源在本机最快。

---

## 二、配置手机推送（也可以直接用网页设置）

网页版：打开 `http://电脑IP:8000/setup`，填完点保存即可，**推荐用这个**。

手动改配置的话，填进 `config.yaml`：

```yaml
notify:
  bark:
    enabled: true
    url: "https://api.day.app/AbCdEf123456"
```

或者设置环境变量 `BARK_URL`，优先级更高（云端用 Secrets 走这条路）。

---

## 三、配置 AI 摘要（免费，可选）

不配也能跑：摘要退化成机翻或原文截断，推送照常。

1. 打开 https://bigmodel.cn 注册
2. 创建 API Key，模型选 **glm-4-flash**（免费）
3. 填进 `config.yaml` 的 `ai.primary.api_key`，或设环境变量 `ZHIPU_API_KEY`

降级链：GLM-4-Flash → 硅基流动免费模型 → 机翻（MyMemory）→ 原文。任何一层挂掉不影响采集与推送。

### 英文消息怎么变成中文

不需要额外配置，默认就开（`translate.enabled: true`）。

- **有 AI key 时**：翻译和摘要合并在同一次调用里完成，标题、摘要、影响判断一起产出，不额外花钱，质量最好
- **没有 AI key 时**：走 MyMemory 免费接口，翻译标题 + 正文前几句。每天上限 `translate.free_daily_limit` 条（默认 150），超了自动停手，不会把接口打到限流
- **两层都不可用时**：保留英文原文，页面上标「原文」，推送里也照常可见

每条英文消息都保留英文原标题（推送里显示为「原文：…」一行，看板上是灰色小字），方便核对与搜索原文。

已入库的历史英文条目可以用工具补翻（**先停程序再跑**，否则会被内存里的旧数据覆盖）：

```bash
python tools/translate_backfill.py          # 补中文标题
python tools/translate_backfill.py --body   # 连正文摘要一起补
```

---

## 四、部署到云端 7×24

1. 在 GitHub 新建一个 **public** 仓库（公开仓库的 Actions 不计分钟数）
2. 把本目录推上去：

```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/你的用户名/仓库名.git
git push -u origin main
```

3. 仓库 Settings → Secrets and variables → Actions，添加：
   - `BARK_URL`：你的 Bark 地址
   - `ZHIPU_API_KEY`：智谱 Key（可选）
4. Settings → Actions → General → Workflow permissions，选 **Read and write permissions**（否则无法提交数据）
5. Actions 页面点 `radar` → `Run workflow` 手动跑一次

6. 打开手机网页版：
   Settings → Pages → Source 选 `Deploy from a branch`，分支 `main`、目录 `/ (root)`
   几分钟后访问 `https://你的用户名.github.io/仓库名/`
   在 Safari 里点分享 → 添加到主屏幕

### 运行节奏

- cron 每 6 小时拉起一次，单次跑 5 小时 50 分，内部每 30 秒抓一轮
- 每天约 4 次重启，每次空约 10 分钟；重启后回溯补抓最近 2 小时，不丢数据
- 想要更快（15 秒、无空档），换一台 50–150 元/年的云服务器，代码不用改

---

## 五、加渠道：改配置就行，不用动代码

`config.yaml` 的 `sources` 里加一条即可：

```yaml
  - name: 中新网滚动
    type: rss
    tier: media
    region: cn
    enabled: true
    interval: 180
    url: "https://www.chinanews.com.cn/rss/scroll-news.xml"
```

加完先跑一次体检，确认新源真能出条目，再等它进流水线：

```bash
python tools/health.py
```

字段说明：

| 字段 | 含义 |
|---|---|
| `type` | `rss` / `sina` / `jin10` / `szse` / `telegram` / `quote` |
| `tier` | `official` 官方 / `exchange` 交易所 / `authority` 权威媒体 / `media` 媒体 / `unverified` 未证实 |
| `region` | `cn` / `intl`，只用于前端筛选，不影响流程 |
| `interval` | 该源的轮询间隔（秒） |

**RSS 一把梭**：绝大多数媒体和官方机构都有 RSS，找到地址填进去就行。
**Telegram 频道**：把 `type` 设为 `telegram`，`channel` 填频道名（不带 @），`enabled` 改 `true`。

---

## 六、调推送量

最常改的三个数字：

```yaml
thresholds:
  push: 68      # >= 这个分数立即推送。嫌吵就调高，嫌漏就调低
  digest: 50    # 进摘要池的门槛
```

建议先跑一周，再根据实际感受调。**这一步只能靠真实使用，不能靠拍脑袋。**

---

## 七、目录结构

```
main.py              入口，长驻轮询
config.yaml          所有配置：源、关键词、阈值
index.html           频道式看板（PWA）
start.bat            电脑端双击启动
radar/
  collectors.py      采集器：RSS / 新浪 / 金十 / 深交所 / Telegram / 行情
  dedupe.py          指纹 + SimHash 聚类
  score.py           打分与分级
  ai.py              AI 摘要三层降级
  translate.py       英文转中文：AI → 机翻 → 原文，带缓存与额度控制
  notify.py          Bark 推送与消息格式
  store.py           JSON 存储
tools/
  health.py          全部渠道体检
  translate_backfill.py  补翻历史英文条目
  compare.py         新旧打分对照
data/
  events.json        事件库（前端读这个）
  seen.json          已见指纹
  translate_cache.json  翻译缓存与当日额度计数
```

---

## 八、消息格式

```
🟠 12:08 央行开展 3000 亿元 MLF 操作

央行今日通过 MLF 投放 3000 亿元，本月到期 2000 亿元，净投放 1000 亿元。

影响（推断）　流动性边际宽松，利多债市与高估值成长
来源：中国人民银行 · 官方
```

事实与推断物理分离：标题正文只做搬运，`影响` 单独标注为推断。

英文源的推送是这样（标题和正文都已译成中文，英文原标题留一行备查）：

```
🟠 13:50 尽管霍尔木兹海峡的威胁日益加剧，但油价仍出现下滑

周三亚洲早盘时段，原油价格走低，延续了近期的跌势……

原文：Oil Prices Slide Despite Mounting Threats in the Strait of Hormuz
来源：OilPrice · 媒体
```

---

## 九、常见问题

**抓不到海外源**：本机网络不可达属正常，云端会补。若云端也失败，换该媒体的其他 RSS 地址。

**收不到推送**：先跑 `--dry-run` 看有没有 L2 事件；再检查 `BARK_URL` 是否填对；Bark 的「历史消息」里能看到投递记录。

**推送太多**：把 `thresholds.push` 从 68 调到 75。

**推送太少**：降到 60，同时检查 `keywords.core` 是否覆盖了你关注的品种。

**Actions 报没有写权限**：Settings → Actions → General → Workflow permissions 选 Read and write。

**数据文件冲突**：`concurrency` 已保证单实例，偶发冲突会自动 rebase 重试。
