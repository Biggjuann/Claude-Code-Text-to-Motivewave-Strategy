"""
Results Manager — CLI tool for managing backtest result folders.

Usage:
    python results_manager.py list                     # List all results with stats
    python results_manager.py list --strategy ifvg     # Filter by strategy name
    python results_manager.py list --sort sharpe       # Sort by metric
    python results_manager.py info lb_short_v7         # Detailed info on one result
    python results_manager.py compare lb_short_v6 lb_short_v7   # Side-by-side compare
    python results_manager.py delete lb_short_v2 lb_short_v3    # Delete folders
    python results_manager.py clean                    # Interactive cleanup of orphan files
    python results_manager.py size                     # Disk usage per folder
"""

import argparse
import os
import sys
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

RESULTS_DIR = Path(__file__).parent / "results"


def parse_pnl(val):
    """Parse realized_pnl column: '1234.50 USD' -> 1234.50"""
    return float(str(val).replace(" USD", "").replace(",", ""))


def load_positions(folder: Path) -> pd.DataFrame | None:
    """Load positions.csv from a result folder, return None if missing."""
    csv_path = folder / "positions.csv"
    if not csv_path.exists():
        return None
    try:
        df = pd.read_csv(csv_path)
        if df.empty or "realized_pnl" not in df.columns:
            return None
        df["pnl"] = df["realized_pnl"].apply(parse_pnl)
        if "ts_closed" in df.columns:
            df["ts_closed"] = pd.to_datetime(df["ts_closed"], utc=True)
        if "ts_opened" in df.columns:
            df["ts_opened"] = pd.to_datetime(df["ts_opened"], utc=True)
        if "duration_ns" in df.columns:
            df["duration_min"] = pd.to_numeric(df["duration_ns"], errors="coerce") / 1e9 / 60
        for col in ("avg_px_open", "avg_px_close", "peak_qty", "realized_return"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception:
        return None


def compute_stats(df: pd.DataFrame) -> dict:
    """Compute key stats from positions DataFrame."""
    pnls = df["pnl"]
    total_pnl = pnls.sum()
    n = len(pnls)
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    win_rate = len(wins) / n * 100 if n > 0 else 0
    gross_w = wins.sum() if len(wins) > 0 else 0
    gross_l = abs(losses.sum()) if len(losses) > 0 else 0
    pf = gross_w / gross_l if gross_l > 0 else float("inf")

    equity = pnls.cumsum()
    peak = equity.cummax()
    dd = (equity - peak).min()

    sharpe = 0.0
    if n > 1 and pnls.std() > 0:
        sharpe = (pnls.mean() / pnls.std()) * np.sqrt(252)

    # Date range
    start_date = ""
    end_date = ""
    if "ts_closed" in df.columns and not df["ts_closed"].isna().all():
        start_date = df["ts_closed"].min().strftime("%Y-%m-%d")
        end_date = df["ts_closed"].max().strftime("%Y-%m-%d")

    # Strategy name from strategy_id column
    strategy = ""
    if "strategy_id" in df.columns:
        strategy = df["strategy_id"].iloc[0].split("-")[0] if len(df) > 0 else ""

    # Direction
    direction = "Mixed"
    if "entry" in df.columns:
        entries = df["entry"].unique()
        if len(entries) == 1:
            direction = entries[0]

    return {
        "trades": n,
        "total_pnl": total_pnl,
        "win_rate": win_rate,
        "profit_factor": pf,
        "sharpe": sharpe,
        "max_dd": dd,
        "avg_win": wins.mean() if len(wins) > 0 else 0,
        "avg_loss": losses.mean() if len(losses) > 0 else 0,
        "wins": len(wins),
        "losses": len(losses),
        "start_date": start_date,
        "end_date": end_date,
        "strategy": strategy,
        "direction": direction,
    }


def get_folder_size(folder: Path) -> int:
    """Return total size in bytes of a folder."""
    total = 0
    for f in folder.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024*1024):.1f} MB"


def list_results(args):
    """List all result folders with summary stats."""
    folders = sorted([f for f in RESULTS_DIR.iterdir() if f.is_dir()])

    if not folders:
        print("No result folders found.")
        return

    rows = []
    for folder in folders:
        df = load_positions(folder)
        if df is None:
            # Check if it has any files at all
            file_count = len(list(folder.rglob("*")))
            if file_count > 0:
                rows.append({
                    "label": folder.name,
                    "trades": 0,
                    "total_pnl": 0,
                    "win_rate": 0,
                    "profit_factor": 0,
                    "sharpe": 0,
                    "max_dd": 0,
                    "start_date": "",
                    "end_date": "",
                    "strategy": "(no positions)",
                    "direction": "",
                    "size": get_folder_size(folder),
                })
            continue

        stats = compute_stats(df)
        stats["label"] = folder.name
        stats["size"] = get_folder_size(folder)
        rows.append(stats)

    if not rows:
        print("No results found.")
        return

    # Filter by strategy name
    if args.strategy:
        search = args.strategy.lower()
        rows = [r for r in rows if search in r["label"].lower() or search in r.get("strategy", "").lower()]

    if not rows:
        print(f"No results matching '{args.strategy}'.")
        return

    # Sort
    sort_key = args.sort if args.sort else "label"
    reverse = sort_key != "label"
    if sort_key == "pnl":
        sort_key = "total_pnl"
    rows.sort(key=lambda r: r.get(sort_key, 0), reverse=reverse)

    # Print table
    print()
    print(f"{'Label':<28} {'Strategy':<22} {'Trades':>6} {'Total P&L':>12} "
          f"{'WR%':>6} {'PF':>6} {'Sharpe':>7} {'Max DD':>11} "
          f"{'Period':<23} {'Size':>8}")
    print("-" * 150)

    total_size = 0
    for r in rows:
        period = ""
        if r.get("start_date"):
            period = f"{r['start_date']} - {r['end_date']}"

        pnl_str = f"${r['total_pnl']:>10,.0f}" if r["trades"] > 0 else "          -"
        wr_str = f"{r['win_rate']:>5.1f}%" if r["trades"] > 0 else "     -"
        pf_str = f"{r['profit_factor']:>5.2f}" if r["trades"] > 0 and r["profit_factor"] < 100 else "     -"
        sh_str = f"{r['sharpe']:>6.2f}" if r["trades"] > 0 else "      -"
        dd_str = f"${r['max_dd']:>9,.0f}" if r["trades"] > 0 else "          -"
        size_str = format_size(r["size"])
        total_size += r.get("size", 0)

        print(f"{r['label']:<28} {r.get('strategy', ''):<22} {r['trades']:>6} {pnl_str} "
              f"{wr_str} {pf_str} {sh_str} {dd_str} "
              f"{period:<23} {size_str:>8}")

    print("-" * 150)
    print(f"  {len(rows)} result folders | Total disk: {format_size(total_size)}")
    print()


def info_result(args):
    """Show detailed info for a single result folder."""
    label = args.label
    folder = RESULTS_DIR / label

    if not folder.exists():
        print(f"Error: '{label}' not found in {RESULTS_DIR}")
        return

    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")

    # List files
    files = sorted(folder.rglob("*"))
    print(f"\n  Files ({len([f for f in files if f.is_file()])}):")
    for f in files:
        if f.is_file():
            rel = f.relative_to(folder)
            print(f"    {rel}  ({format_size(f.stat().st_size)})")
    print(f"  Total: {format_size(get_folder_size(folder))}")

    # Stats
    df = load_positions(folder)
    if df is not None:
        stats = compute_stats(df)
        print(f"\n  Strategy:       {stats['strategy']}")
        print(f"  Direction:      {stats['direction']}")
        print(f"  Period:         {stats['start_date']} to {stats['end_date']}")
        print(f"  Trades:         {stats['trades']} ({stats['wins']} W / {stats['losses']} L)")
        print(f"  Total P&L:      ${stats['total_pnl']:,.2f}")
        print(f"  Win Rate:       {stats['win_rate']:.1f}%")
        pf = stats['profit_factor']
        print(f"  Profit Factor:  {pf:.2f}" if pf < 100 else "  Profit Factor:  inf")
        print(f"  Sharpe:         {stats['sharpe']:.2f}")
        print(f"  Max Drawdown:   ${stats['max_dd']:,.2f}")
        print(f"  Avg Win:        ${stats['avg_win']:,.2f}")
        print(f"  Avg Loss:       ${stats['avg_loss']:,.2f}")
        if stats['avg_loss'] != 0:
            print(f"  Win/Loss Ratio: {stats['avg_win'] / abs(stats['avg_loss']):.2f}x")
    else:
        print("\n  No positions.csv found — cannot compute stats.")
    print()


def compare_results(args):
    """Side-by-side comparison of multiple result folders."""
    labels = args.labels

    all_stats = []
    for label in labels:
        folder = RESULTS_DIR / label
        if not folder.exists():
            print(f"Warning: '{label}' not found, skipping.")
            continue
        df = load_positions(folder)
        if df is None:
            print(f"Warning: '{label}' has no positions.csv, skipping.")
            continue
        stats = compute_stats(df)
        stats["label"] = label
        all_stats.append(stats)

    if len(all_stats) < 2:
        print("Need at least 2 valid results to compare.")
        return

    # Print comparison table
    col_width = max(20, max(len(s["label"]) for s in all_stats) + 2)
    metrics = [
        ("Strategy", "strategy", "s"),
        ("Direction", "direction", "s"),
        ("Period", None, "period"),
        ("Trades", "trades", "d"),
        ("Wins", "wins", "d"),
        ("Losses", "losses", "d"),
        ("Total P&L", "total_pnl", "$"),
        ("Win Rate", "win_rate", "%"),
        ("Profit Factor", "profit_factor", "f"),
        ("Sharpe", "sharpe", "f"),
        ("Max Drawdown", "max_dd", "$"),
        ("Avg Win", "avg_win", "$"),
        ("Avg Loss", "avg_loss", "$"),
    ]

    print()
    # Header
    header = f"{'Metric':<20}"
    for s in all_stats:
        header += f"  {s['label']:>{col_width}}"
    print(header)
    print("-" * (20 + (col_width + 2) * len(all_stats)))

    for name, key, fmt in metrics:
        row = f"{name:<20}"
        vals = []
        for s in all_stats:
            if fmt == "period":
                val = f"{s['start_date']} - {s['end_date']}"
            elif fmt == "s":
                val = str(s.get(key, ""))
            elif fmt == "d":
                val = f"{s.get(key, 0)}"
            elif fmt == "$":
                val = f"${s.get(key, 0):,.2f}"
            elif fmt == "%":
                val = f"{s.get(key, 0):.1f}%"
            elif fmt == "f":
                v = s.get(key, 0)
                val = f"{v:.2f}" if v < 100 else "inf"
            else:
                val = str(s.get(key, ""))
            vals.append(val)
            row += f"  {val:>{col_width}}"
        print(row)

    # Winner row for key metrics
    print("-" * (20 + (col_width + 2) * len(all_stats)))
    pnls = [s["total_pnl"] for s in all_stats]
    best_idx = pnls.index(max(pnls))
    row = f"{'>> Best P&L':<20}"
    for i, s in enumerate(all_stats):
        marker = "  <<<" if i == best_idx else ""
        row += f"  {'':>{col_width}}" if i != best_idx else f"  {'<<< WINNER':>{col_width}}"
    print(row)
    print()


def delete_results(args):
    """Delete specified result folders."""
    labels = args.labels
    force = args.force

    to_delete = []
    for label in labels:
        folder = RESULTS_DIR / label
        if not folder.exists():
            print(f"  '{label}' not found, skipping.")
            continue
        to_delete.append(folder)

    if not to_delete:
        print("Nothing to delete.")
        return

    # Show what will be deleted
    print("\nFolders to delete:")
    total_size = 0
    for folder in to_delete:
        size = get_folder_size(folder)
        total_size += size
        file_count = len(list(folder.rglob("*")))
        print(f"  {folder.name}/  ({file_count} files, {format_size(size)})")
    print(f"\nTotal: {len(to_delete)} folders, {format_size(total_size)}")

    if not force:
        confirm = input("\nDelete these folders? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return

    for folder in to_delete:
        shutil.rmtree(folder)
        print(f"  Deleted: {folder.name}/")
    print(f"\nDone. Freed {format_size(total_size)}.")


def clean_results(args):
    """Interactive cleanup — find orphan files and empty/small folders."""
    print("\n--- Orphan files (not in a subfolder) ---")
    orphans = [f for f in RESULTS_DIR.iterdir() if f.is_file()]
    if orphans:
        for f in orphans:
            print(f"  {f.name}  ({format_size(f.stat().st_size)})")
        total = sum(f.stat().st_size for f in orphans)
        print(f"  Total: {len(orphans)} files, {format_size(total)}")
    else:
        print("  None found.")

    print("\n--- Folders with no positions.csv ---")
    no_pos = []
    for folder in sorted(RESULTS_DIR.iterdir()):
        if folder.is_dir() and not (folder / "positions.csv").exists():
            no_pos.append(folder)
            print(f"  {folder.name}/  ({format_size(get_folder_size(folder))})")
    if not no_pos:
        print("  None found.")

    print("\n--- Small folders (< 10 KB, likely empty runs) ---")
    small = []
    for folder in sorted(RESULTS_DIR.iterdir()):
        if folder.is_dir():
            size = get_folder_size(folder)
            if size < 10240:
                small.append(folder)
                print(f"  {folder.name}/  ({format_size(size)})")
    if not small:
        print("  None found.")

    print()


def size_results(args):
    """Show disk usage per folder, sorted by size."""
    folders = sorted(RESULTS_DIR.iterdir())
    rows = []
    for f in folders:
        if f.is_dir():
            size = get_folder_size(f)
            rows.append((f.name, size))
        elif f.is_file():
            rows.append((f.name, f.stat().st_size))

    rows.sort(key=lambda r: r[1], reverse=True)

    total = sum(r[1] for r in rows)
    print(f"\n{'Name':<40} {'Size':>10}")
    print("-" * 52)
    for name, size in rows:
        bar_len = int(size / max(total, 1) * 30)
        bar = "#" * bar_len
        print(f"{name:<40} {format_size(size):>10}  {bar}")
    print("-" * 52)
    print(f"{'TOTAL':<40} {format_size(total):>10}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Results Manager — manage backtest result folders",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python results_manager.py list                          List all with stats
  python results_manager.py list --strategy lb_short      Filter by name
  python results_manager.py list --sort sharpe            Sort by Sharpe
  python results_manager.py list --sort pnl               Sort by P&L
  python results_manager.py info lb_short_v7              Detailed view
  python results_manager.py compare lb_short_v6 lb_short_v7
  python results_manager.py delete lb_short_v2 lb_short_v3
  python results_manager.py delete lb_short_v2 --force    Skip confirmation
  python results_manager.py clean                         Find orphans
  python results_manager.py size                          Disk usage
""",
    )
    sub = parser.add_subparsers(dest="command")

    # list
    p_list = sub.add_parser("list", aliases=["ls"], help="List all result folders with stats")
    p_list.add_argument("--strategy", "-s", help="Filter by strategy/label name")
    p_list.add_argument("--sort", choices=["label", "trades", "pnl", "win_rate", "profit_factor", "sharpe", "max_dd", "size"],
                        default="label", help="Sort column")

    # info
    p_info = sub.add_parser("info", help="Detailed info on one result folder")
    p_info.add_argument("label", help="Result folder name")

    # compare
    p_comp = sub.add_parser("compare", aliases=["cmp"], help="Side-by-side comparison")
    p_comp.add_argument("labels", nargs="+", help="Result folder names to compare")

    # delete
    p_del = sub.add_parser("delete", aliases=["rm"], help="Delete result folders")
    p_del.add_argument("labels", nargs="+", help="Result folder names to delete")
    p_del.add_argument("--force", "-f", action="store_true", help="Skip confirmation")

    # clean
    sub.add_parser("clean", help="Find orphan files and empty folders")

    # size
    sub.add_parser("size", aliases=["du"], help="Disk usage per folder")

    args = parser.parse_args()

    if args.command in ("list", "ls"):
        list_results(args)
    elif args.command == "info":
        info_result(args)
    elif args.command in ("compare", "cmp"):
        compare_results(args)
    elif args.command in ("delete", "rm"):
        delete_results(args)
    elif args.command == "clean":
        clean_results(args)
    elif args.command in ("size", "du"):
        size_results(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
