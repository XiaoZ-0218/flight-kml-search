# flight-kml-search

> 给定**航班号 + 日期**，找到对应的航班实例，并把实际飞行轨迹保存为 **KML 文件**（Google Earth 可直接打开、可播放动画）。
>
> 全程只用**免费、免注册**的数据源。配套 agent skill — 同目录下的 [SKILL.md](SKILL.md) 描述了如何以 agent 身份调用本程序。

---

## 特性

- ✈️ **搜索 → 列班次 → 下载 KML** 三段式 CLI；同一天有多个匹配班次时列出表格，由调用方挑选，程序不擅自决定。
- 🌐 **多源自动 failover** — 「找航班」和「取轨迹」两层各有多个免费源，失败自动切换（详见下文数据源表）。
- 🕐 **时间感知选路** — 最近约 24 小时的航班走 OpenSky 匿名接口；更早的日期自动切换到 ADSBexchange 每日 arrivals CSV 存档（可追溯到 2024-07，轨迹存档最老到 2016 年）。
- 🗺️ **高分辨率轨迹** — 优先使用 adsb.lol 的 5 秒级全天 ADS-B trace，按起降时刻切片，比 OpenSky 的稀疏轨迹点数多一个量级。
- 🔤 **航班号自动转换** — IATA 航班号（UA888、3U8735）自动映射到 ICAO 呼号（UAL888、CSC8735），内置 941 家航司对照表；查不到的航司退化为按数字段模糊匹配并列出全部候选。
- 🛡️ **严格的出口策略** — 仅 https、主机白名单、拒绝环回/私网/保留地址。
- 🧪 **离线测试套件** — stdlib `unittest`，49 个用例，无网络依赖。
- 🪶 **零安装** — 通过 [PEP 723](https://peps.python.org/pep-0723/) 内联依赖声明，`uv run` 临时解决唯一依赖（`requests`），无需 clone 或建 venv。

---

## 快速开始

需要 [uv](https://github.com/astral-sh/uv)（`brew install uv`），或 Python ≥ 3.9 + `pip install requests`。

```bash
# 搜索某航班在某天的班次（列表输出到 stderr）
uv run main.py UA888 2026-08-15

# 下载第 1 个班次的轨迹 KML（文件路径输出到 stdout，便于脚本串联）
uv run main.py UA888 2026-08-15 --pick 1

# 大致知道起飞时刻时收窄扫描窗口（UTC），省 OpenSky 配额
uv run main.py UA888 2026-08-15 --utc-from 17:00 --utc-to 23:59

# 强制指定发现源
uv run main.py DL2237 2026-07-01 --source csv --pick 1
```

生成的 KML 包含带时间戳和高度的 `gx:Track`（Google Earth 里可回放），以及兼容普通查看器的 `LineString` 兜底。

---

## 数据源与覆盖

查询分两层，每层独立 failover：

**第一层 · 发现**（航班号 + 日期 → 机身 hex + 起降时刻）：

| 源 | 覆盖 | 说明 |
| --- | --- | --- |
| `opensky` | 匿名约最近 24h；配免费凭据可查历史 | 匿名每日配额很小，429 即当日用尽 |
| `csv` | 2024-07 起，**临近当下有数周缺口** | ADSBexchange 每日 arrivals CSV（约 13 MB/天，缓存于 `~/.cache/flight-kml-search`），按**到达日**归档 |

`--source auto`（默认）：日期在匿名可达范围或已配凭据时用 OpenSky，否则用 CSV；OpenSky 查不到且日期够老时自动回退 CSV。

**第二层 · 取轨迹**（hex + 时刻 → 位置点）：

| 源 | 覆盖 | 说明 |
| --- | --- | --- |
| `adsb.lol` 全天 trace | 约 2023 → 昨天 | 5 秒级分辨率，无配额 |
| `adsbexchange-samples` | 2016 → 约 2024 | 存档站，同格式 |
| `opensky` track | 近期 | 兜底，点较稀 |

**已知覆盖盲区**：ADS-B 是众包数据——大洋上空、偏远地区可能有断点；中国大陆上空接收机稀少，国内段经常缺失；部分机身被机主屏蔽。查到班次但无轨迹时程序以退出码 3 报错。

---

## 配额与限制（发布/分享前请读）

所有限制都落在**运行者**一侧，与 skill 作者无关：

- **OpenSky 匿名配额按调用者出口 IP 计**，每日重置。每个使用者消耗的是自己的额度。
- **OpenSky 凭据**（`OPENSKY_CLIENT_ID` / `OPENSKY_CLIENT_SECRET`）是使用者本机的环境变量，从 [opensky-network.org](https://opensky-network.org) 免费注册后在账户后台创建 API client 即可获得。**请勿把任何凭据打包进发布物**。
- **adsb.lol / samples.adsbexchange.com** 是志愿者运营的静态托管，无账号无配额。请保持礼貌使用：本工具已内置 CSV 按天缓存、1.2 秒请求间隔、429 退避重试；请勿用于批量爬取全量数据。
- **数据条款**：OpenSky 与 ADSBexchange 的数据定位为非商用 / 研究用途。个人下载航班轨迹自用没有问题；把数据二次打包分发或商用需自行确认各站条款。

---

## 作为 agent skill 使用

本目录同时是一个自包含的 Claude / ZCode skill：把整个目录放到 `~/.zcode/skills/flight-kml-search/`（或 `~/.agents/skills/`）即可被 agent 触发，调用约定见 [SKILL.md](SKILL.md)（flags、退出码、班次挑选启发式）。

---

## 开发

```bash
# 离线测试（49 个用例，无网络）
uv run --with requests python -m unittest discover -s tests -t .

# 重新生成航司对照表（数据集更新后）
# 1. 下载 https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat 到 scripts/
# 2. 运行：
python3 scripts/gen_airlines.py
```

目录结构：

```
main.py               入口（PEP 723 内联依赖）
flight_kml/
  cli.py              参数解析与 搜索→挑选→下载 工作流
  opensky.py          OpenSky REST 客户端（OAuth2、窗口扫描、429 退避）
  arrivals.py         ADSBexchange arrivals CSV 发现源（按天缓存）
  traces.py           全天 trace 拉取 / 解析 / 按时刻切片，多 host failover
  ident.py            航班号解析、IATA→ICAO 匹配（含人工校订 CURATED 表）
  airlines.py         航司对照表（941 条，脚本生成，勿手改）
  kml.py              KML 生成（gx:Track + LineString）
  http.py             出口策略（https 白名单、拒绝内网地址）
tests/                离线测试
scripts/              开发工具（航司表生成器）
SKILL.md              agent 调用约定
```

## 退出码

| Code | 含义 |
| --- | --- |
| 0 | 列出 / 下载成功 |
| 1 | 未找到匹配航班 |
| 2 | 输入错误、API 错误或该日期无可用发现源 |
| 3 | 找到航班但所有源都无轨迹（覆盖盲区） |

## License

[MIT](LICENSE)。注意：MIT 只覆盖本仓库的代码；通过本工具获取的航班数据受其来源站点条款约束（见上文「配额与限制」）。
