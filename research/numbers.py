"""Extract and compute deterministic financial numbers and flags from financials.tables.

FINN Research Engine - Numbers Section.
Python only, no LLM.
Computes:
  - Snapshot: latest quarter revenue & PAT with YoY, TTM revenue & PAT, latest operating margin.
  - Trajectory: 3-year and 5-year revenue & PAT CAGR from annual P&L, 5-year annual operating margins.
  - Balance sheet: borrowings, debt-to-equity, working-capital / cash-conversion-cycle days.
  - Cash quality: 3-year cumulative CFO / PAT ratio.
  - Flags: cash conversion < 70%, D/E > 1 (non-lenders), margin drop >= 3 pts over 3y,
    working capital days increase >= 20 over 3y.
"""

import sys
from pathlib import Path

# Remove script directory from sys.path to avoid shadowing standard library 'numbers'
_script_dir = str(Path(__file__).resolve().parent)
while _script_dir in sys.path:
    sys.path.remove(_script_dir)

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Pre-import standard library numbers and decimal
import numbers as _stdlib_numbers
import decimal
from typing import Any
import argparse
import datetime
import logging
import math

# Ensure utf-8 stdout/stderr on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pipeline.db import select, upsert

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("numbers")


def find_row(table: dict[str, Any], candidate_labels: list[str]) -> tuple[str, list[Any]] | None:
    """Find a row matching candidate labels case-insensitively."""
    rows = table.get("rows", [])
    for r in rows:
        lbl = (r.get("label") or "").strip().lower()
        for cand in candidate_labels:
            cand_lower = cand.strip().lower()
            if cand_lower == lbl or lbl.startswith(cand_lower):
                return r.get("label", ""), r.get("values", [])
    return None


def calculate_cagr(start_val: float | None, end_val: float | None, years: int) -> float | None:
    """Calculate compound annual growth rate as a percentage."""
    if start_val is None or end_val is None or years <= 0:
        return None
    if start_val <= 0 or end_val <= 0:
        return None
    try:
        return ((end_val / start_val) ** (1.0 / years) - 1.0) * 100.0
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def compute_numbers_for_ticker(ticker: str) -> dict[str, Any]:
    """Compute deterministic financial numbers and flags for an NSE ticker."""
    rows = select("financials", ticker=ticker)
    if not rows:
        raise ValueError(f"No financials found for {ticker} in Supabase financials table.")

    fin_row = rows[0]
    tables = fin_row.get("tables", {})
    basis = fin_row.get("basis", "consolidated")

    # Detect lender
    comp_rows = select("companies", ticker=ticker)
    sector = (comp_rows[0].get("sector") or "") if comp_rows else ""
    pl_tbl = tables.get("profit_loss", {})
    pl_rows = pl_tbl.get("rows", [])
    is_lender = (
        sector.lower() in ["nbfc", "banking", "finance", "financial services"]
        or any("financing profit" in (r.get("label") or "").lower() for r in pl_rows)
    )

    q_tbl = tables.get("quarterly_results", {})
    bs_tbl = tables.get("balance_sheet", {})
    rat_tbl = tables.get("ratios", {})
    cf_tbl = tables.get("cash_flow", {})

    q_cols = q_tbl.get("columns", [])
    pl_cols = pl_tbl.get("columns", [])
    bs_cols = bs_tbl.get("columns", [])
    rat_cols = rat_tbl.get("columns", [])
    cf_cols = cf_tbl.get("columns", [])

    # Filter annual columns in profit_loss (excluding 'TTM')
    pl_annual_cols = [c for c in pl_cols if c.strip().upper() != "TTM"]

    # -------------------------------------------------------------
    # 1. Snapshot
    # -------------------------------------------------------------
    snapshot: dict[str, Any] = {}

    rev_labels = ["Sales", "Revenue", "Revenue from operations"]
    pat_labels = ["Net Profit", "PAT", "Profit after tax"]
    opm_labels = ["OPM %", "Operating Profit Margin", "Operating Margin %"]

    q_rev_match = find_row(q_tbl, rev_labels)
    q_pat_match = find_row(q_tbl, pat_labels)
    q_opm_match = find_row(q_tbl, opm_labels)

    if q_cols:
        latest_q_idx = len(q_cols) - 1
        latest_q_col = q_cols[latest_q_idx]

        # Latest Quarter Revenue
        if q_rev_match:
            r_label, r_vals = q_rev_match
            if latest_q_idx < len(r_vals) and r_vals[latest_q_idx] is not None:
                cur_val = float(r_vals[latest_q_idx])
                yoy_growth = None
                prior_q_col = None
                if latest_q_idx >= 4 and (latest_q_idx - 4) < len(r_vals):
                    prior_val = r_vals[latest_q_idx - 4]
                    if prior_val is not None and prior_val != 0:
                        yoy_growth = ((cur_val - float(prior_val)) / abs(float(prior_val))) * 100.0
                        prior_q_col = q_cols[latest_q_idx - 4]
                snapshot["latest_quarter_revenue"] = {
                    "value": cur_val,
                    "unit": "₹ cr",
                    "quarter": latest_q_col,
                    "yoy_growth_pct": round(yoy_growth, 2) if yoy_growth is not None else None,
                    "source": {
                        "table": "quarterly_results",
                        "column": latest_q_col,
                        "prior_column": prior_q_col,
                    },
                }

        # Latest Quarter PAT
        if q_pat_match:
            p_label, p_vals = q_pat_match
            if latest_q_idx < len(p_vals) and p_vals[latest_q_idx] is not None:
                cur_pat = float(p_vals[latest_q_idx])
                pat_yoy_growth = None
                prior_pat_q_col = None
                if latest_q_idx >= 4 and (latest_q_idx - 4) < len(p_vals):
                    prior_pat = p_vals[latest_q_idx - 4]
                    if prior_pat is not None and prior_pat != 0:
                        pat_yoy_growth = ((cur_pat - float(prior_pat)) / abs(float(prior_pat))) * 100.0
                        prior_pat_q_col = q_cols[latest_q_idx - 4]
                snapshot["latest_quarter_pat"] = {
                    "value": cur_pat,
                    "unit": "₹ cr",
                    "quarter": latest_q_col,
                    "yoy_growth_pct": round(pat_yoy_growth, 2) if pat_yoy_growth is not None else None,
                    "source": {
                        "table": "quarterly_results",
                        "column": latest_q_col,
                        "prior_column": prior_pat_q_col,
                    },
                }

        # Latest Operating Margin
        if is_lender:
            snapshot["latest_operating_margin"] = {
                "value": None,
                "note": "lender: different metrics",
            }
        elif q_opm_match:
            _, opm_vals = q_opm_match
            if latest_q_idx < len(opm_vals) and opm_vals[latest_q_idx] is not None:
                snapshot["latest_operating_margin"] = {
                    "value": float(opm_vals[latest_q_idx]),
                    "unit": "%",
                    "quarter": latest_q_col,
                    "source": {"table": "quarterly_results", "column": latest_q_col},
                }

    # Trailing 12-Month Revenue & PAT
    pl_rev_match = find_row(pl_tbl, rev_labels)
    pl_pat_match = find_row(pl_tbl, pat_labels)

    ttm_col_idx = None
    for idx, c in enumerate(pl_cols):
        if c.strip().upper() == "TTM":
            ttm_col_idx = idx
            break

    # TTM Revenue
    if ttm_col_idx is not None and pl_rev_match:
        _, pl_r_vals = pl_rev_match
        if ttm_col_idx < len(pl_r_vals) and pl_r_vals[ttm_col_idx] is not None:
            snapshot["ttm_revenue"] = {
                "value": float(pl_r_vals[ttm_col_idx]),
                "unit": "₹ cr",
                "source": {"table": "profit_loss", "column": "TTM"},
            }
    elif q_rev_match and len(q_cols) >= 4:
        _, q_r_vals = q_rev_match
        last_4_vals = q_r_vals[-4:]
        if all(v is not None for v in last_4_vals):
            snapshot["ttm_revenue"] = {
                "value": sum(float(v) for v in last_4_vals),
                "unit": "₹ cr",
                "source": {"table": "quarterly_results", "columns": q_cols[-4:]},
            }

    # TTM PAT
    if ttm_col_idx is not None and pl_pat_match:
        _, pl_p_vals = pl_pat_match
        if ttm_col_idx < len(pl_p_vals) and pl_p_vals[ttm_col_idx] is not None:
            snapshot["ttm_pat"] = {
                "value": float(pl_p_vals[ttm_col_idx]),
                "unit": "₹ cr",
                "source": {"table": "profit_loss", "column": "TTM"},
            }
    elif q_pat_match and len(q_cols) >= 4:
        _, q_p_vals = q_pat_match
        last_4_vals = q_p_vals[-4:]
        if all(v is not None for v in last_4_vals):
            snapshot["ttm_pat"] = {
                "value": sum(float(v) for v in last_4_vals),
                "unit": "₹ cr",
                "source": {"table": "quarterly_results", "columns": q_cols[-4:]},
            }

    # -------------------------------------------------------------
    # 2. Trajectory
    # -------------------------------------------------------------
    trajectory: dict[str, Any] = {}

    if len(pl_annual_cols) >= 4 and pl_rev_match:
        _, pl_r_vals = pl_rev_match
        # Map values by col name
        col_to_val = {col: pl_r_vals[i] for i, col in enumerate(pl_cols) if i < len(pl_r_vals)}
        end_col = pl_annual_cols[-1]
        start_3y_col = pl_annual_cols[-4]
        v_end = col_to_val.get(end_col)
        v_3y = col_to_val.get(start_3y_col)
        cagr_3y = calculate_cagr(float(v_3y) if v_3y is not None else None, float(v_end) if v_end is not None else None, 3)
        if cagr_3y is not None:
            trajectory["revenue_cagr_3y"] = {
                "value": round(cagr_3y, 2),
                "unit": "%",
                "source": {"table": "profit_loss", "start_column": start_3y_col, "end_column": end_col},
            }

        if len(pl_annual_cols) >= 6:
            start_5y_col = pl_annual_cols[-6]
            v_5y = col_to_val.get(start_5y_col)
            cagr_5y = calculate_cagr(float(v_5y) if v_5y is not None else None, float(v_end) if v_end is not None else None, 5)
            if cagr_5y is not None:
                trajectory["revenue_cagr_5y"] = {
                    "value": round(cagr_5y, 2),
                    "unit": "%",
                    "source": {"table": "profit_loss", "start_column": start_5y_col, "end_column": end_col},
                }

    if len(pl_annual_cols) >= 4 and pl_pat_match:
        _, pl_p_vals = pl_pat_match
        col_to_val = {col: pl_p_vals[i] for i, col in enumerate(pl_cols) if i < len(pl_p_vals)}
        end_col = pl_annual_cols[-1]
        start_3y_col = pl_annual_cols[-4]
        v_end = col_to_val.get(end_col)
        v_3y = col_to_val.get(start_3y_col)
        cagr_3y = calculate_cagr(float(v_3y) if v_3y is not None else None, float(v_end) if v_end is not None else None, 3)
        if cagr_3y is not None:
            trajectory["pat_cagr_3y"] = {
                "value": round(cagr_3y, 2),
                "unit": "%",
                "source": {"table": "profit_loss", "start_column": start_3y_col, "end_column": end_col},
            }

        if len(pl_annual_cols) >= 6:
            start_5y_col = pl_annual_cols[-6]
            v_5y = col_to_val.get(start_5y_col)
            cagr_5y = calculate_cagr(float(v_5y) if v_5y is not None else None, float(v_end) if v_end is not None else None, 5)
            if cagr_5y is not None:
                trajectory["pat_cagr_5y"] = {
                    "value": round(cagr_5y, 2),
                    "unit": "%",
                    "source": {"table": "profit_loss", "start_column": start_5y_col, "end_column": end_col},
                }

    # Operating Margin for each of the last 5 years
    if is_lender:
        trajectory["operating_margins_5y"] = {
            "values": None,
            "note": "lender: different metrics",
        }
    else:
        pl_opm_match = find_row(pl_tbl, opm_labels)
        if pl_opm_match:
            _, opm_vals = pl_opm_match
            col_to_opm = {col: opm_vals[i] for i, col in enumerate(pl_cols) if i < len(opm_vals)}
            recent_5_cols = pl_annual_cols[-5:] if len(pl_annual_cols) >= 5 else pl_annual_cols
            margin_list = []
            for col in recent_5_cols:
                val = col_to_opm.get(col)
                if val is not None:
                    margin_list.append({
                        "year": col,
                        "margin_pct": float(val),
                        "source": {"table": "profit_loss", "column": col},
                    })
            trajectory["operating_margins_5y"] = margin_list

    # -------------------------------------------------------------
    # 3. Balance Sheet
    # -------------------------------------------------------------
    balance_sheet: dict[str, Any] = {}

    borrowing_labels = ["Borrowings", "Borrowing", "Total Borrowings"]
    equity_labels = ["Equity Capital", "Share Capital"]
    reserves_labels = ["Reserves", "Other Equity", "Reserves & Surplus", "Reserves and Surplus"]

    bs_bor_match = find_row(bs_tbl, borrowing_labels)
    bs_eq_match = find_row(bs_tbl, equity_labels)
    bs_res_match = find_row(bs_tbl, reserves_labels)

    if bs_cols:
        latest_bs_idx = len(bs_cols) - 1
        latest_bs_col = bs_cols[latest_bs_idx]

        cur_borrowings = None
        if bs_bor_match:
            _, b_vals = bs_bor_match
            if latest_bs_idx < len(b_vals) and b_vals[latest_bs_idx] is not None:
                cur_borrowings = float(b_vals[latest_bs_idx])
                balance_sheet["borrowings"] = {
                    "value": cur_borrowings,
                    "unit": "₹ cr",
                    "source": {"table": "balance_sheet", "column": latest_bs_col},
                }

        # Debt to Equity
        if is_lender:
            balance_sheet["debt_to_equity"] = {
                "value": None,
                "note": "lender: different metrics",
            }
        elif cur_borrowings is not None and bs_eq_match and bs_res_match:
            _, eq_vals = bs_eq_match
            _, res_vals = bs_res_match
            if (
                latest_bs_idx < len(eq_vals)
                and eq_vals[latest_bs_idx] is not None
                and latest_bs_idx < len(res_vals)
                and res_vals[latest_bs_idx] is not None
            ):
                eq_val = float(eq_vals[latest_bs_idx])
                res_val = float(res_vals[latest_bs_idx])
                total_equity = eq_val + res_val
                if total_equity > 0:
                    de_ratio = cur_borrowings / total_equity
                    balance_sheet["debt_to_equity"] = {
                        "value": round(de_ratio, 2),
                        "borrowings": cur_borrowings,
                        "total_equity": total_equity,
                        "equity_capital": eq_val,
                        "reserves": res_val,
                        "source": {"table": "balance_sheet", "column": latest_bs_col},
                    }

    # Working Capital Days or Cash Conversion Cycle
    wc_match = find_row(rat_tbl, ["Working Capital Days"])
    ccc_match = find_row(rat_tbl, ["Cash Conversion Cycle"])

    if rat_cols:
        latest_rat_idx = len(rat_cols) - 1
        latest_rat_col = rat_cols[latest_rat_idx]

        if wc_match:
            _, wc_vals = wc_match
            if latest_rat_idx < len(wc_vals) and wc_vals[latest_rat_idx] is not None:
                balance_sheet["working_capital_days"] = {
                    "value": float(wc_vals[latest_rat_idx]),
                    "unit": "days",
                    "source": {"table": "ratios", "column": latest_rat_col},
                }

        if ccc_match:
            _, ccc_vals = ccc_match
            if latest_rat_idx < len(ccc_vals) and ccc_vals[latest_rat_idx] is not None:
                balance_sheet["cash_conversion_cycle_days"] = {
                    "value": float(ccc_vals[latest_rat_idx]),
                    "unit": "days",
                    "source": {"table": "ratios", "column": latest_rat_col},
                }

    # -------------------------------------------------------------
    # 4. Cash Quality (3-year CFO / Net Profit)
    # -------------------------------------------------------------
    cash_quality: dict[str, Any] = {}

    if is_lender:
        cash_quality["cash_conversion_3y"] = {
            "value": None,
            "note": "lender: different metrics",
        }
    else:
        cfo_match = find_row(cf_tbl, ["Cash from Operating Activity", "Cash from operations", "Operating Cash Flow"])
        if cfo_match and pl_pat_match and cf_cols and pl_cols:
            _, cfo_vals = cfo_match
            _, pat_vals = pl_pat_match

            # Find matching common 3 annual years
            common_years = [c for c in cf_cols if c in pl_cols and c.strip().upper() != "TTM"]
            if len(common_years) >= 3:
                last_3_years = common_years[-3:]
                cf_col_to_val = {col: cfo_vals[i] for i, col in enumerate(cf_cols) if i < len(cfo_vals)}
                pl_col_to_val = {col: pat_vals[i] for i, col in enumerate(pl_cols) if i < len(pat_vals)}

                cfo_3y = [cf_col_to_val.get(y) for y in last_3_years]
                pat_3y = [pl_col_to_val.get(y) for y in last_3_years]

                if all(v is not None for v in cfo_3y) and all(v is not None for v in pat_3y):
                    sum_cfo = sum(float(v) for v in cfo_3y)
                    sum_pat = sum(float(v) for v in pat_3y)
                    if sum_pat != 0:
                        ratio = sum_cfo / sum_pat
                        cash_quality["cash_conversion_3y"] = {
                            "ratio": round(ratio, 3),
                            "percentage": round(ratio * 100.0, 1),
                            "sum_cfo": round(sum_cfo, 1),
                            "sum_pat": round(sum_pat, 1),
                            "years": last_3_years,
                            "source": {
                                "cash_flow_table": "cash_flow",
                                "profit_loss_table": "profit_loss",
                                "columns": last_3_years,
                            },
                        }

    # -------------------------------------------------------------
    # 5. Flags by Rule
    # -------------------------------------------------------------
    flags: list[dict[str, Any]] = []

    # Rule 1: Cash conversion < 70%
    if is_lender:
        flags.append({
            "flag": "cash_conversion_lt_70",
            "triggered": False,
            "note": "lender: different metrics",
        })
    else:
        cc_info = cash_quality.get("cash_conversion_3y")
        if cc_info and cc_info.get("ratio") is not None:
            r = cc_info["ratio"]
            pct = cc_info["percentage"]
            trig = r < 0.70
            sum_c = cc_info["sum_cfo"]
            sum_p = cc_info["sum_pat"]
            yrs = ", ".join(cc_info["years"])
            flags.append({
                "flag": "cash_conversion_lt_70",
                "triggered": trig,
                "value": pct,
                "threshold": 70.0,
                "details": f"3-year CFO/PAT ratio is {pct}% (< 70%): CFO ₹{sum_c:,.0f} cr vs PAT ₹{sum_p:,.0f} cr over {yrs}",
                "numbers": {
                    "ratio": r,
                    "percentage": pct,
                    "sum_cfo": sum_c,
                    "sum_pat": sum_p,
                    "years": cc_info["years"],
                },
            })

    # Rule 2: Debt to equity > 1 (non-lenders only)
    if is_lender:
        flags.append({
            "flag": "debt_to_equity_gt_1",
            "triggered": False,
            "note": "lender: different metrics",
        })
    else:
        de_info = balance_sheet.get("debt_to_equity")
        if de_info and de_info.get("value") is not None:
            de_val = de_info["value"]
            trig = de_val > 1.0
            borr = de_info["borrowings"]
            eq = de_info["total_equity"]
            col = de_info["source"]["column"]
            flags.append({
                "flag": "debt_to_equity_gt_1",
                "triggered": trig,
                "value": de_val,
                "threshold": 1.0,
                "details": f"Debt-to-equity is {de_val:.2f} (> 1.0): Borrowings ₹{borr:,.0f} cr vs Equity ₹{eq:,.0f} cr ({col})",
                "numbers": {
                    "debt_to_equity": de_val,
                    "borrowings": borr,
                    "equity": eq,
                    "column": col,
                },
            })

    # Rule 3: Margin down >= 3 points over 3 years
    if is_lender:
        flags.append({
            "flag": "margin_down_ge_3_pts_3y",
            "triggered": False,
            "note": "lender: different metrics",
        })
    else:
        opm_hist = trajectory.get("operating_margins_5y")
        if isinstance(opm_hist, list) and len(opm_hist) >= 4:
            m_latest_obj = opm_hist[-1]
            m_3y_obj = opm_hist[-4]
            m_latest = m_latest_obj["margin_pct"]
            m_3y = m_3y_obj["margin_pct"]
            drop = m_latest - m_3y
            trig = drop <= -3.0
            flags.append({
                "flag": "margin_down_ge_3_pts_3y",
                "triggered": trig,
                "change_points": round(drop, 2),
                "threshold": -3.0,
                "details": f"Operating margin changed {drop:+.1f} pts over 3 years: {m_latest:.1f}% ({m_latest_obj['year']}) vs {m_3y:.1f}% ({m_3y_obj['year']})",
                "numbers": {
                    "latest_margin": m_latest,
                    "latest_year": m_latest_obj["year"],
                    "prior_margin": m_3y,
                    "prior_year": m_3y_obj["year"],
                    "change": drop,
                },
            })

    # Rule 4: Working-capital days up >= 20 over 3 years
    if rat_cols and wc_match:
        _, wc_vals = wc_match
        col_to_wc = {col: wc_vals[i] for i, col in enumerate(rat_cols) if i < len(wc_vals)}
        if len(rat_cols) >= 4:
            latest_col = rat_cols[-1]
            prior_3y_col = rat_cols[-4]
            wc_lat = col_to_wc.get(latest_col)
            wc_3y = col_to_wc.get(prior_3y_col)
            if wc_lat is not None and wc_3y is not None:
                increase = float(wc_lat) - float(wc_3y)
                trig = increase >= 20.0
                flags.append({
                    "flag": "working_capital_days_up_ge_20_3y",
                    "triggered": trig,
                    "change_days": round(increase, 1),
                    "threshold": 20.0,
                    "details": f"Working capital days changed {increase:+.0f} days over 3 years: {float(wc_lat):.0f} days ({latest_col}) vs {float(wc_3y):.0f} days ({prior_3y_col})",
                    "numbers": {
                        "latest_days": float(wc_lat),
                        "latest_column": latest_col,
                        "prior_days": float(wc_3y),
                        "prior_column": prior_3y_col,
                        "change": increase,
                    },
                })

    result_data = {
        "basis": basis,
        "is_lender": is_lender,
        "snapshot": snapshot,
        "trajectory": trajectory,
        "balance_sheet": balance_sheet,
        "cash_quality": cash_quality,
        "flags": flags,
    }

    # Save to research table
    upsert(
        "research",
        {
            "ticker": ticker,
            "section": "numbers",
            "content": result_data,
            "sources": [
                {"table": "financials", "ticker": ticker, "basis": basis},
            ],
            "model": "python",
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
        on_conflict="ticker,section",
    )
    logger.info("Saved numbers section for %s", ticker)

    return result_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute deterministic financial numbers and flags.")
    parser.add_argument("--ticker", required=True, help="NSE ticker symbol (e.g. DIXON, BAJFINANCE)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    data = compute_numbers_for_ticker(args.ticker)
    print("=" * 70)
    print(f"NUMBERS & FLAGS REPORT: {args.ticker} (Lender: {data['is_lender']})")
    print("=" * 70)
    print("\nSnapshot:")
    for k, v in data["snapshot"].items():
        print(f"  {k}: {v}")
    print("\nTrajectory:")
    for k, v in data["trajectory"].items():
        print(f"  {k}: {v}")
    print("\nBalance Sheet:")
    for k, v in data["balance_sheet"].items():
        print(f"  {k}: {v}")
    print("\nCash Quality:")
    for k, v in data["cash_quality"].items():
        print(f"  {k}: {v}")
    print("\nFlags:")
    for f in data["flags"]:
        flag_status = "TRIGGERED" if f.get("triggered") else ("SKIPPED" if f.get("note") else "OK")
        print(f"  [{flag_status}] {f['flag']}: {f.get('details') or f.get('note')}")
    print("=" * 70)
