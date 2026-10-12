#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
我的投资组合 - 数据更新接口

用法示例（在仓库根目录运行）:
  # 按当日涨跌幅更新净值（单位 %，正负均可）
  python scripts/update_portfolio.py record --change 2.5
  python scripts/update_portfolio.py record --change -1.3

  # 直接指定当日净值
  python scripts/update_portfolio.py record --nav 1.0250

  # 指定日期（默认今天）
  python scripts/update_portfolio.py record --change 2.5 --date 2026-10-13

  # 更新持仓（全量覆盖，权重之和应为 1）
  python scripts/update_portfolio.py holding "长鑫科技:1.0" "贵州茅台:0.2" "现金:-0.2"

  # 更新后自动 git commit + push（上线）
  python scripts/update_portfolio.py record --change 2.5 --push

数据文件: data/portfolio.json
"""
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "portfolio.json"


def load_data():
    if not DATA_FILE.exists():
        sys.exit(f"错误: 找不到数据文件 {DATA_FILE}")
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def save_data(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def cmd_record(args, data):
    today = args.date or datetime.date.today().isoformat()
    hist = data["nav_history"]
    prices = data.get("price_history", [])

    modes = [m for m in (args.nav, args.change, args.price) if m is not None]
    if len(modes) != 1:
        sys.exit("错误: --nav / --change / --price 只能三选一")

    if args.nav is not None:
        nav = round(float(args.nav), 4)
    elif args.change is not None:
        if not hist:
            sys.exit("错误: 净值历史为空，请先用 --nav 建立基期")
        prev_navs = [r for r in hist if r["date"] < today]
        if not prev_navs:
            sys.exit(f"错误: {today} 之前没有净值记录")
        nav = round(prev_navs[-1]["nav"] * (1 + float(args.change) / 100), 4)
    else:
        # 价格模式: 按收盘价计算净值，自动处理除权除息
        if not hist or not prices:
            sys.exit("错误: price_history 为空，无法按价格计算净值")
        prev_prices = [p for p in prices if p["date"] < today]
        if not prev_prices:
            sys.exit(f"错误: {today} 之前没有价格记录")
        prev_price = prev_prices[-1]["price"]
        # 复权: 除息(现金分红) + 除权(送转股)
        if args.dividend is not None:
            prev_price -= float(args.dividend)
        if args.split is not None:
            prev_price /= (1 + float(args.split))
        prev_navs = [r for r in hist if r["date"] < today]
        nav = round(prev_navs[-1]["nav"] * float(args.price) / prev_price, 4)
        prices = [p for p in prices if p["date"] != today]
        prices.append({"date": today, "price": round(float(args.price), 4)})
        prices.sort(key=lambda p: p["date"])
        data["price_history"] = prices
        print(f"[价格] 前收(复权后): {prev_price:.4f} -> 今收: {float(args.price):.4f}")

    if today in [r["date"] for r in hist]:
        hist = [r for r in hist if r["date"] != today]
        action = "覆盖"
    else:
        action = "新增"

    hist.append({"date": today, "nav": nav})
    hist.sort(key=lambda r: r["date"])
    data["nav_history"] = hist
    data["updated_at"] = today
    save_data(data)
    print(f"[OK] 已{action} {today} 净值: {nav:.4f}（共 {len(hist)} 条记录）")


def cmd_holding(args, data):
    if not args.holdings:
        sys.exit("错误: 请提供持仓，格式: 名称:权重，如 \"长鑫科技:1.0\"")
    old = {h["name"]: h for h in data.get("holdings", [])}
    holdings = []
    for item in args.holdings:
        try:
            name, weight = item.rsplit(":", 1)
            name = name.strip()
            weight = float(weight)
        except ValueError:
            sys.exit(f'错误: 无法解析 "{item}"，正确格式: 名称:权重')
        # 已存在的持仓保留 ticker/note 等字段，仅更新权重
        h = old.get(name, {"name": name})
        h["weight"] = weight
        holdings.append(h)
    total = sum(h["weight"] for h in holdings)
    if abs(total - 1.0) > 0.001:
        print(f"[警告] 持仓权重之和为 {total:.4f}，不等于 1，请确认是否故意留出现金/杠杆敞口")
    data["holdings"] = holdings
    data["updated_at"] = datetime.date.today().isoformat()
    save_data(data)
    print("[OK] 持仓已更新:")
    for h in holdings:
        print(f"  - {h['name']}: {h['weight'] * 100:.1f}%")


def push():
    cmds = [
        ["git", "add", str(DATA_FILE.relative_to(ROOT))],
        ["git", "commit", "-m", f"update portfolio {datetime.date.today().isoformat()}"],
        ["git", "push"],
    ]
    for c in cmds:
        r = subprocess.run(c, cwd=ROOT)
        if r.returncode != 0:
            sys.exit(f"错误: {' '.join(c)} 执行失败")
    print("[OK] 已提交并推送到 GitHub，稍后 Pages 会自动更新")


def main():
    parser = argparse.ArgumentParser(description="个人投资组合数据更新接口")
    sub = parser.add_subparsers(dest="command", required=True)

    p_rec = sub.add_parser("record", help="记录一条净值")
    p_rec.add_argument("--nav", type=float, help="当日净值（如 1.0250）")
    p_rec.add_argument("--change", type=float, help="当日涨跌幅%%（如 2.5 或 -1.3）")
    p_rec.add_argument("--price", type=float, help="当日收盘价，自动按复权计算净值（推荐）")
    p_rec.add_argument("--dividend", type=float, help="当日除息: 每股现金分红(元)，与 --price 同用")
    p_rec.add_argument("--split", type=float, help="当日除权: 每股送转比(如0.5=10送5)，与 --price 同用")
    p_rec.add_argument("--date", help="日期 YYYY-MM-DD，默认今天")
    p_rec.add_argument("--push", action="store_true", help="更新后 git commit + push")

    p_hold = sub.add_parser("holding", help="全量更新持仓")
    p_hold.add_argument("holdings", nargs="+", help='持仓列表，格式: "名称:权重"')
    p_hold.add_argument("--push", action="store_true", help="更新后 git commit + push")

    args, data = parser.parse_args(), load_data()
    if args.command == "record":
        cmd_record(args, data)
    else:
        cmd_holding(args, data)

    if args.push:
        push()


if __name__ == "__main__":
    main()
