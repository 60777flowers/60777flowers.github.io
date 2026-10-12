#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自动更新投资组合（持仓数据驱动，支持任意多标的与调仓）

流程: 读取 data/portfolio.json 的 holdings ->
      抓取每只持仓的行情（现价 + 昨收） ->
      按权重加权计算组合当日涨跌幅（昨收为交易所除权参考价，天然复权）->
      录入净值 -> (可选) git push

用法:
  python scripts/auto_update.py            # 抓当日行情并录入
  python scripts/auto_update.py --push     # 录入后自动 git commit + push
  python scripts/auto_update.py --dry-run  # 只看不写
  python scripts/auto_update.py --force    # 当天已有记录也强制覆盖

调仓: 修改 data/portfolio.json 的 holdings（或用 update_portfolio.py holding 命令），
      每个持仓加 "qt_code" 字段（腾讯/新浪行情代码，如 sh688825、sz000001）。
      无 qt_code 的持仓（如现金）视为当日收益 0。

数据源（自动降级）: 腾讯行情 -> 新浪行情
"""
import datetime
import json
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "portfolio.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_tencent(qt_code):
    """返回 dict(name, price, prev_close, date) 或 None"""
    try:
        r = requests.get(f"https://qt.gtimg.cn/q={qt_code}", headers=UA, timeout=15)
        r.raise_for_status()
        r.encoding = "gbk"
        body = r.text.split('"')[1] if '"' in r.text else ""
        f = body.split("~")
        if len(f) < 31 or not f[3]:
            return None
        ts = f[30]  # yyyymmddHHMMSS
        return {
            "name": f[1],
            "price": float(f[3]),
            "prev_close": float(f[4]),  # 除权日为除权参考价(含复权)
            "date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
        }
    except Exception as e:
        print(f"[腾讯源] {qt_code} 失败: {e}")
        return None


def fetch_sina(qt_code):
    try:
        r = requests.get(
            f"https://hq.sinajs.cn/list={qt_code}",
            headers={**UA, "Referer": "https://finance.sina.com.cn"},
            timeout=15,
        )
        r.raise_for_status()
        r.encoding = "gbk"
        body = r.text.split('"')[1] if '"' in r.text else ""
        f = body.split(",")
        if len(f) < 31 or not f[3]:
            return None
        return {
            "name": f[0],
            "price": float(f[3]),
            "prev_close": float(f[2]),  # 昨收(除权日为除权参考价)
            "date": f[30],
        }
    except Exception as e:
        print(f"[新浪源] {qt_code} 失败: {e}")
        return None


def fetch_quote(qt_code):
    return fetch_tencent(qt_code) or fetch_sina(qt_code)


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    push = "--push" in args
    force = "--force" in args

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    holdings = data.get("holdings", [])
    traded = [h for h in holdings if h.get("qt_code")]
    if not traded:
        sys.exit("[错误] holdings 中没有任何带 qt_code 的持仓，无法自动更新")

    today = datetime.date.today().isoformat()

    # 幂等: 当天已有 auto 快照则跳过（快照=auto 成功运行的标志）
    # 注意: 基期占位记录(无快照)会被当日真实收盘数据覆盖
    if not force:
        if any(s["date"] == today for s in data.get("snapshots", [])):
            print(f"[跳过] {today} 已有自动更新快照，无需重复更新（--force 可覆盖）")
            return

    # 抓取全部持仓行情
    quotes = {}
    for h in traded:
        q = fetch_quote(h["qt_code"])
        if q is None:
            sys.exit(f"[错误] 持仓 {h['name']}({h['qt_code']}) 行情获取失败，为保证一致性本次不更新")
        quotes[h["name"]] = q
        print(f"[行情] {h['name']}({h['qt_code']}) 现价 {q['price']} / 昨收 {q['prev_close']} ({q['date']})")

    # 交易日校验：任一行情日期非今日（休市/未更新）则跳过
    for name, q in quotes.items():
        if q["date"] != today:
            sys.exit(f"[跳过] {name} 行情日期 {q['date']} 不是今天（{today}），休市或数据未更新")

    # 按权重加权计算组合当日涨跌幅（无代码持仓如现金计 0 收益）
    total_weight = sum(h["weight"] for h in holdings)
    if abs(total_weight) < 1e-12:
        sys.exit("[错误] 持仓权重之和为 0")
    port_ret = 0.0
    for h in holdings:
        q = quotes.get(h["name"])
        if q and q["prev_close"]:
            port_ret += (h["weight"] / total_weight) * (q["price"] / q["prev_close"] - 1)
    port_ret *= 100
    print(f"[计算] 组合当日涨跌幅: {port_ret:+.4f}%")

    # 价格快照 + 持仓快照（含权重与代码，可用于日后重算净值）
    import copy
    snap = {
        "date": today,
        "prices": {h["name"]: quotes[h["name"]]["price"] for h in traded},
        "holdings": copy.deepcopy(holdings),
    }
    print(f"[快照] 价格: {json.dumps(snap['prices'], ensure_ascii=False)} | 持仓: "
          + ", ".join(f"{h['name']} {h['weight']*100:.1f}%" for h in holdings))

    if dry:
        print(f"[演练] 将执行: record --change {port_ret:.4f}")
        return

    cmd = [sys.executable, str(ROOT / "scripts" / "update_portfolio.py"),
           "record", "--change", f"{port_ret:.6f}"]
    if push:
        cmd.append("--push")
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        sys.exit(r.returncode)

    # 写入快照（record 成功后）
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    snaps = [s for s in data.get("snapshots", []) if s["date"] != today]
    snaps.append(snap)
    snaps.sort(key=lambda s: s["date"])
    data["snapshots"] = snaps
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[OK] 价格快照已存档")


if __name__ == "__main__":
    main()
