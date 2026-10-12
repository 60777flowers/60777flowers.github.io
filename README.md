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

数据文件：`data/portfolio.json`。基期 2026-10-12，净值 1.0000 对应长鑫科技（688825.SH）
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

### 持仓管理

```bash
# 全量更新持仓（已有持仓的 ticker 等字段会保留）
python scripts/update_portfolio.py holding "长鑫科技:1.0"
```

### 更新后直接上线

```bash
python scripts/update_portfolio.py record --price 51.88 --push
```

前端已做防缓存处理（fetch 加时间戳参数），push 后 GitHub Pages 部署完成即可看到最新数据。

## 历史版本

原版 Hexo 博客（2022 版）备份于本地 `博客原版存档_20261012/` 与 git 标签 `v1-original-backup`。
