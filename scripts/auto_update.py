#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自动更新投资组合（收盘价驱动，支持任意多标的、调仓与跨日补录）

设计要点（都是踩过的坑）:
  1) 用「日K线」而不是实时行情判断交易日: 实时行情的日期字段在集合竞价时段
     (9:15 起)就会翻到"今天"并显示竞价撮合价，2026-10-14 曾被误当作收盘价录入。
     现在以「K线最新一根的日期 + 北京时间 15:05 收盘门禁」双重确认，彻底杜绝
     盘中/竞价数据入库。
  2) GitHub Actions 的 schedule 实测有 2~9 小时排队延迟，触发时刻不可控，
     因此脚本设计为"任意时刻运行都安全": 未收盘只读不写；收盘后写入当日；
     若整个晚上都被延迟错过，之后的首个运行会按 K 线日期自动补录前一交易日。
  3) 收益按「前复权收盘价」计算(自动处理分红送转)；基准价取「最后一条净值
     记录日」的 K 线收盘价，因此即使中间隔了若干漏录日，链式相乘依然正确。

流程: 读取 holdings -> 抓每只持仓的日K线(前复权) ->
      确定目标交易日 D(全部持仓 K 线的最新共同日期，且该日已收盘) ->
      计算「最后净值记录日 -> D」的组合累计收益 ->
      record --date D --change <收益> -> 写价格快照 -> (可选) git push

用法:
  python scripts/auto_update.py            # 收盘后运行则录入当日净值
  python scripts/auto_update.py --push     # 录入后自动 git commit + push
  python scripts/auto_update.py --dry-run  # 只看不写
  python scripts/auto_update.py --force    # 当日已有快照也强制重算

调仓: 用 update_portfolio.py holding 命令或直接改 data/portfolio.json 的
      holdings，每个持仓加 "qt_code"(腾讯代码，如 sh688825、hk00700)。
      无 qt_code 的持仓(如现金)按收益 0 处理。

数据源: 腾讯日K线(前复权) https://web.ifzq.gtimg.cn
"""
import copy
import datetime
import json
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "portfolio.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
BJT = datetime.timezone(datetime.timedelta(hours=8))


def bj_now():
    """GitHub runner 的本地时区是 UTC，必须显式换算成北京时间。"""
    return datetime.datetime.now(datetime.timezone.utc).astimezone(BJT)


def load_data():
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def save_data(data):
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def fetch_kline(qt_code, days=120):
    """腾讯日K线(前复权)。返回 [(日期, 收盘价)] 升序，含当日实时K(若已生成)。

    前复权价格自动处理分红送转；最新一根的收盘价在盘中为实时价、
    收盘后为当日收盘价。获取失败返回 None。
    """
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={qt_code},day,,,{days},qfq")
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.raise_for_status()
        d = (r.json().get("data") or {}).get(qt_code) or {}
        bars = d.get("qfqday") or d.get("day") or []
        k = [(b[0], float(b[2])) for b in bars if len(b) >= 3]
        return k or None
    except Exception as e:
        print(f"[K线源] {qt_code} 获取失败: {e}")
        return None


def close_on_or_before(kline, date):
    """kline 中不晚于 date 的最后一根收盘价（停牌日自动取上一根）。"""
    last = None
    for d, c in kline:
        if d <= date:
            last = c
        else:
            break
    return last


def git_push():
    """提交并推送数据文件（无改动时跳过，避免空提交导致 CI 失败）"""
    rel = str(DATA_FILE.relative_to(ROOT))

    def run(c):
        return subprocess.run(c, cwd=ROOT)

    run(["git", "add", rel])
    if run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        print("[跳过] 数据无变化，无需提交")
        return
    if run(["git", "commit", "-m", f"update portfolio {bj_now().date().isoformat()}"]).returncode != 0:
        sys.exit("错误: git commit 失败")
    if run(["git", "push"]).returncode != 0:
        sys.exit("错误: git push 失败")
    print("[OK] 已提交并推送到 GitHub，稍后 Pages 会自动更新")


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    push = "--push" in args
    force = "--force" in args

    data = load_data()
    holdings = data.get("holdings", [])
    traded = [h for h in holdings if h.get("qt_code")]
    if not traded:
        sys.exit("[错误] holdings 中没有任何带 qt_code 的持仓，无法自动更新")

    now = bj_now()
    today = now.date().isoformat()

    # 1) 抓全部持仓的日K线
    klines = {}
    for h in traded:
        k = fetch_kline(h["qt_code"])
        if not k:
            sys.exit(f"[错误] 持仓 {h['name']}({h['qt_code']}) 日K线获取失败，为保证一致性本次不更新")
        klines[h["name"]] = k
        print(f"[K线] {h['name']}({h['qt_code']}) 最新 {k[-1][0]} 收 {k[-1][1]:.2f}（共 {len(k)} 根）")

    # 2) 目标交易日 = 全部持仓都已出K线的最新共同日期
    d_target = min(k[-1][0] for k in klines.values())

    # 3) 收盘门禁: 目标日是"今天"时，必须过了北京时间 15:05
    #    (A 股 15:00 收盘，留 5 分钟给收盘数据落库；科创板盘后固定价交易不改收盘价)
    if d_target == today:
        if now.hour < 15 or (now.hour == 15 and now.minute < 5):
            print(f"[跳过] {today} 尚未收盘（北京时间 {now:%H:%M}），收盘后会自动录入，本次不写入")
            return
    # d_target < today: 属于漏录的历史交易日，直接补录

    # 4) 幂等: 目标日已有快照则跳过（快照 = auto 成功运行的标志）
    if not force and any(s.get("date") == d_target for s in data.get("snapshots", [])):
        print(f"[跳过] {d_target} 已有自动更新快照，无需重复更新（--force 可覆盖）")
        return

    hist = data.get("nav_history", [])
    if not hist:
        sys.exit("[错误] nav_history 为空，请先建立基期")
    base_date = hist[-1]["date"]
    if d_target <= base_date:
        print(f"[跳过] 目标日 {d_target} 不晚于最后净值记录 {base_date}，无需更新")
        return

    # 5) 组合自 base_date 以来的累计收益（按当前权重；前复权口径；
    #    基准价取 K 线在 base_date 的收盘价，跨漏录日依然正确）
    total_weight = sum(h["weight"] for h in holdings)
    if abs(total_weight) < 1e-12:
        sys.exit("[错误] 持仓权重之和为 0")
    port_ret = 0.0
    for h in holdings:
        k = klines.get(h["name"])
        if k is None:
            continue  # 无行情代码的持仓（现金等）计 0 收益
        base_close = close_on_or_before(k, base_date)
        last_close = close_on_or_before(k, d_target)
        if base_close is None or last_close is None or base_close <= 0:
            sys.exit(f"[错误] {h['name']} 的K线未覆盖 {base_date}~{d_target}，为避免净值错链本次不更新")
        port_ret += (h["weight"] / total_weight) * (last_close / base_close - 1)
    port_ret *= 100
    print(f"[计算] {base_date} -> {d_target} 组合累计收益: {port_ret:+.4f}%")

    snap = {
        "date": d_target,
        "prices": {h["name"]: close_on_or_before(klines[h["name"]], d_target) for h in traded},
        "holdings": copy.deepcopy(holdings),
    }
    print(f"[快照] 价格: {json.dumps(snap['prices'], ensure_ascii=False)} | 持仓: "
          + ", ".join(f"{h['name']} {h['weight'] * 100:.1f}%" for h in holdings))

    if dry:
        print(f"[演练] 将执行: record --date {d_target} --change {port_ret:.4f}")
        return

    cmd = [sys.executable, str(ROOT / "scripts" / "update_portfolio.py"),
           "record", "--date", d_target, "--change", f"{port_ret:.6f}"]
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        sys.exit(r.returncode)

    # 写入快照（record 成功后、push 之前，确保快照随本次提交入库）
    data = load_data()
    snaps = [s for s in data.get("snapshots", []) if s.get("date") != d_target]
    snaps.append(snap)
    snaps.sort(key=lambda s: s["date"])
    data["snapshots"] = snaps

    # 单票组合顺带维护 price_history，保证 --price 手工录入模式的链式基准不脱节
    if len(traded) == 1:
        ph = [p for p in data.get("price_history", []) if p["date"] != d_target]
        ph.append({"date": d_target, "price": snap["prices"][traded[0]["name"]]})
        ph.sort(key=lambda p: p["date"])
        data["price_history"] = ph

    save_data(data)
    print("[OK] 价格快照已存档")

    if push:
        git_push()


if __name__ == "__main__":
    main()
