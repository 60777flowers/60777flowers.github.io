# 杨凯盛的个人博客 (60777flowers.github.io)

GitHub Pages 静态博客，纯 HTML/CSS/JS，无构建依赖。

## 页面结构

| 页面 | 说明 |
|------|------|
| `index.html` | 首页：关于我 / 博客文章 / 投资组合 三大板块 |
| `about.html` | 关于我 |
| `blog.html` | 博客文章列表 |
| `post.html?id=<文章id>` | 文章详情（数据在 `js/data.js`） |
| `portfolio.html` | 投资组合：净值走势、持仓、历史净值 |

## 写新文章

编辑 `js/data.js`，在 `window.POSTS` 数组头部追加：

```js
{
  id: "2026-10-12-my-new-post",   // 唯一id（用作URL参数）
  title: "标题",
  date: "2026-10-12",
  tag: "标签",
  excerpt: "摘要（卡片显示）",
  content: ["第一段", "第二段", ...]
}
```

## 更新投资组合

数据文件：`data/portfolio.json`。基期 2026-10-09，净值 1.0000 对应长鑫科技（688825.SH）
2026-10-09 收盘价 **51.00 元**。

### 推荐用法：按收盘价录入（自动复权）

```bash
# 每个交易日收盘后，录入当日收盘价，脚本自动计算净值
python scripts/update_portfolio.py record --price 51.88

# 遇到除息日（每股现金分红 X 元）
python scripts/update_portfolio.py record --price 50.20 --dividend 1.0

# 遇到送转除权日（如 10 送 5 即 split=0.5）
python scripts/update_portfolio.py record --price 35.60 --split 0.5
```

### 手动模式

```bash
# 按涨跌幅（单位%）
python scripts/update_portfolio.py record --change 2.5

# 直接给净值
python scripts/update_portfolio.py record --nav 1.0250

# 指定日期（默认今天）
python scripts/update_portfolio.py record --price 51.88 --date 2026-10-13
```

### 持仓管理（调仓）

```bash
# 全量更新持仓（已有持仓的 ticker/note 等字段会保留）
# 格式: 名称:权重[:行情代码]，行情代码用于每日自动更新（腾讯/新浪代码，如 sh688825、sz000001）
python scripts/update_portfolio.py holding "长鑫科技:1.0:sh688825"

# 调仓示例: 60% 长鑫 + 40% 茅台（无代码的持仓如"现金"视为当日收益 0）
python scripts/update_portfolio.py holding "长鑫科技:0.6:sh688825" "贵州茅台:0.4:sh600519"
```

## 每日自动更新（GitHub Actions）

已配置 `.github/workflows/update-portfolio.yml`：**每个交易日北京时间 15:35 与 20:00 自动运行**，
抓取全部持仓的最新行情，按权重加权计算组合当日涨跌幅并录入净值（昨收为交易所除权参考价，
分红送转日自动复权），随后自动 commit + push，无需任何手动操作。

原理与命令（本地亦可手动跑）：

```bash
python scripts/auto_update.py --push   # 抓行情 -> 算净值 -> 推送
python scripts/auto_update.py --dry-run # 只看不算
```

特性：
- 持仓数据驱动：调仓后自动适应新持仓（依据 `qt_code` 字段）
- 幂等：当天已录入则跳过，`--force` 可覆盖（基期占位记录会在当日收盘后被真实数据覆盖）
- 休市日自动跳过（行情日期非当日）
- 行情源自动降级（腾讯 -> 新浪），任一持仓失败则整体不更新（保证一致性）
- 每日快照存档于 `snapshots` 字段

## 数据完整性与净值重算

`data/portfolio.json` 中保存了三类历史数据，支持日后按任意口径重算净值：

| 字段 | 内容 | 用途 |
|------|------|------|
| `snapshots` | 每日：各持仓收盘价 + **当日完整持仓（名称/权重/代码）** | 任意历史日期的持仓与价格快照，重算净值的依据 |
| `holding_history` | 每次调仓：变更时间 + 变更前完整持仓 | 调仓审计，回溯每次调仓时点 |
| `nav_history` / `price_history` | 每日净值 / 单票价格记录 | 当前净值口径的原始结果 |

重算示例：若需按新口径（如改用后复权、剔除某标的）重新计算，可从 `snapshots`
读取逐日持仓与价格重新推导，或写脚本将 `holdings` 恢复为某日快照后继续记录。

### 更新后直接上线

```bash
python scripts/update_portfolio.py record --price 51.88 --push
```

前端已做防缓存处理（fetch 加时间戳参数），push 后 GitHub Pages 部署完成即可看到最新数据。

## 历史版本

原版 Hexo 博客（2022 版）备份于本地 `博客原版存档_20261012/` 与 git 标签 `v1-original-backup`。
